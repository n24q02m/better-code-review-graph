"""SHARES_STATE edges link a writer of module-level state to its readers."""

import tree_sitter_language_pack as tslp

from better_code_review_graph.parser import _collect_module_state, _scan_state_access


def _root(source: bytes):
    return tslp.get_parser("python").parse(source).root_node


def test_module_level_assignment_is_a_direct_child_of_module():
    """A top-level binding is an ``assignment`` directly under ``module``.

    Every later step dispatches on this type name, and a wrong name matches
    nothing rather than raising, so the whole feature would emit no edges and
    report no error. Pinning the shape here turns a silent miss into one
    failing test naming the type it actually saw.
    """
    source = b"REGISTRY = {}\n\n\ndef read_it():\n    return REGISTRY\n"
    root = _root(source)

    top_level = [c.type for c in root.children]
    assert "assignment" in top_level, top_level

    assignment = next(c for c in root.children if c.type == "assignment")
    left = assignment.child_by_field_name("left")
    assert left is not None
    assert left.type == "identifier"
    assert source[left.start_byte : left.end_byte] == b"REGISTRY"


def test_annotated_assignment_keeps_the_plain_assignment_shape():
    source = b"REGISTRY: dict[str, int] = {}\n"
    root = _root(source)

    assert [c.type for c in root.children] == ["assignment"]
    left = root.children[0].child_by_field_name("left")
    assert left is not None
    assert left.type == "identifier"


def test_tuple_binding_puts_targets_in_a_pattern_list():
    source = b"_CACHE, _MISSES = {}, 0\n"
    root = _root(source)

    left = root.children[0].child_by_field_name("left")
    assert left is not None
    assert left.type == "pattern_list"
    assert [c.type for c in left.children if c.type == "identifier"] == [
        "identifier",
        "identifier",
    ]


def test_augmented_assignment_is_a_separate_node_type():
    """``X += 1`` is ``augmented_assignment``, not ``assignment``.

    Anything that recognises rebinding by matching ``assignment`` alone reads
    this as a plain use of ``X`` and records a read where a write belongs,
    which points the resulting edge backwards.
    """
    source = b"def bump():\n    global COUNT\n    COUNT += 1\n"
    body = _root(source).children[0].child_by_field_name("body")
    assert body is not None

    types = [c.type for c in body.children]
    assert "augmented_assignment" in types, types
    assert "assignment" not in types, types

    aug = next(c for c in body.children if c.type == "augmented_assignment")
    left = aug.child_by_field_name("left")
    assert left is not None
    assert left.type == "identifier"


def test_global_declaration_is_its_own_statement():
    source = b"def w():\n    global R\n    R = {}\n"
    body = _root(source).children[0].child_by_field_name("body")
    assert body is not None

    stmt = next(c for c in body.children if c.type == "global_statement")
    names = [
        source[c.start_byte : c.end_byte]
        for c in stmt.children
        if c.type == "identifier"
    ]
    assert names == [b"R"]


def test_decorated_function_is_wrapped_before_the_definition():
    """A decorated function sits under ``decorated_definition``.

    Scanning ``module`` children for ``function_definition`` alone would skip
    every decorated function in the file.
    """
    source = b"@deco\ndef f():\n    return R\n"
    root = _root(source)

    assert [c.type for c in root.children] == ["decorated_definition"]
    inner = [c.type for c in root.children[0].children]
    assert "function_definition" in inner, inner


def test_attribute_and_keyword_argument_hold_a_bare_identifier():
    """``obj.REGISTRY`` and ``f(REGISTRY=1)`` both contain an ``identifier``.

    Neither is a use of the module-level name, so a scan that counts every
    ``identifier`` it walks past would invent readers.
    """
    attr_src = b"def m():\n    return obj.REGISTRY\n"
    attr = (
        _root(attr_src).children[0].child_by_field_name("body").children[0].children[1]
    )
    assert attr.type == "attribute"
    assert attr.child_by_field_name("object").type == "identifier"
    assert attr.child_by_field_name("attribute").type == "identifier"

    kw_src = b"def k():\n    return f(REGISTRY=1)\n"
    call = _root(kw_src).children[0].child_by_field_name("body").children[0].children[1]
    kwarg = call.child_by_field_name("arguments").children[1]
    assert kwarg.type == "keyword_argument"
    assert kwarg.child_by_field_name("name").type == "identifier"


def test_collects_only_module_level_names():
    source = (
        b"REGISTRY = {}\n"
        b"_CACHE, _MISSES = {}, 0\n"
        b"\n"
        b"def f():\n"
        b"    local_only = 1\n"
        b"    return local_only\n"
        b"\n"
        b"class C:\n"
        b"    attr = 2\n"
    )
    names = _collect_module_state(_root(source), source, "python")
    assert names == {"REGISTRY", "_CACHE", "_MISSES"}


def test_collects_annotated_module_binding():
    source = b"REGISTRY: dict[str, int] = {}\n"
    assert _collect_module_state(_root(source), source, "python") == {"REGISTRY"}


def test_non_python_returns_empty():
    source = b"const x = 1;\n"
    root = tslp.get_parser("javascript").parse(source).root_node
    assert _collect_module_state(root, source, "javascript") == set()


def _functions(source: bytes) -> list:
    return [c for c in _root(source).children if c.type == "function_definition"]


def test_reads_and_writes_are_separated():
    source = (
        b"REGISTRY = {}\n"
        b"\n"
        b"def writer():\n"
        b"    global REGISTRY\n"
        b"    REGISTRY = {}\n"
        b"\n"
        b"def reader():\n"
        b"    return REGISTRY\n"
    )
    funcs = _functions(source)

    reads_w, writes_w = _scan_state_access(funcs[0], source, {"REGISTRY"})
    assert writes_w == {"REGISTRY"}
    assert reads_w == set()

    reads_r, writes_r = _scan_state_access(funcs[1], source, {"REGISTRY"})
    assert reads_r == {"REGISTRY"}
    assert writes_r == set()


def test_shadowed_parameter_is_not_shared_state():
    source = b"REGISTRY = {}\n\n\ndef takes_it(REGISTRY):\n    return REGISTRY\n"
    reads, writes = _scan_state_access(_functions(source)[0], source, {"REGISTRY"})
    assert reads == set()
    assert writes == set()


def test_annotated_and_splat_parameters_also_shadow():
    source = (
        b"REGISTRY = {}\n"
        b"CACHE = {}\n"
        b"\n"
        b"def takes_them(REGISTRY: dict, *CACHE):\n"
        b"    return REGISTRY, CACHE\n"
    )
    reads, writes = _scan_state_access(
        _functions(source)[0], source, {"REGISTRY", "CACHE"}
    )
    assert reads == set()
    assert writes == set()


def test_augmented_assignment_is_a_write_not_a_read():
    """``COUNT += 1`` under ``global`` rebinds the module name.

    Matching only ``assignment`` records this as a read, which reverses the
    edge: the function that changes the value would be listed as depending on
    it instead of the other way round.
    """
    source = b"COUNT = 0\n\n\ndef bump():\n    global COUNT\n    COUNT += 1\n"
    reads, writes = _scan_state_access(_functions(source)[0], source, {"COUNT"})
    assert writes == {"COUNT"}
    assert reads == set()


def test_rebinding_without_global_is_a_local_not_a_write():
    """Assigning a name without ``global`` creates a local that shadows it.

    Python binds the name to the function for its whole body, so the module
    value is neither read nor replaced. Counting it as a write would make
    every function holding a same-named local a writer of shared state.
    """
    source = b"REGISTRY = {}\n\n\ndef local_only():\n    REGISTRY = {}\n    return REGISTRY\n"
    reads, writes = _scan_state_access(_functions(source)[0], source, {"REGISTRY"})
    assert writes == set()
    assert reads == set()


def test_attribute_and_keyword_names_are_not_reads():
    """``obj.REGISTRY`` and ``f(REGISTRY=1)`` do not read the module name."""
    source = (
        b"REGISTRY = {}\n"
        b"\n"
        b"def unrelated(obj):\n"
        b"    f(REGISTRY=1)\n"
        b"    return obj.REGISTRY\n"
    )
    reads, writes = _scan_state_access(_functions(source)[0], source, {"REGISTRY"})
    assert reads == set()
    assert writes == set()


def test_reading_through_an_attribute_call_still_counts():
    source = b"REGISTRY = {}\n\n\ndef lookup(key):\n    return REGISTRY.get(key)\n"
    reads, writes = _scan_state_access(_functions(source)[0], source, {"REGISTRY"})
    assert reads == {"REGISTRY"}
    assert writes == set()
