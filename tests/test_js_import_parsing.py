from better_code_review_graph.parser import CodeParser


def test_js_import_parsing(tmp_path):
    parser = CodeParser()

    # Create dummy modules so resolution works
    (tmp_path / "module-a.js").write_text("")
    (tmp_path / "module-b.js").write_text("")
    (tmp_path / "module-c.js").write_text("")
    (tmp_path / "module-d.js").write_text("")

    js_file = tmp_path / "test.js"
    js_file.write_text("""
import defaultExport from './module-a';
import { name1, name2 as alias2 } from './module-b';
import { name3 } from './module-c';
import default2, { name4 } from './module-d';

function test() {
    name1();
    alias2();
    name3();
    name4();
    defaultExport();
    default2();
}
""")

    nodes, edges = parser.parse_file(js_file)

    calls = [e for e in edges if e.kind == "CALLS"]
    call_targets = {e.target for e in calls}

    assert str((tmp_path / "module-a.js").resolve()) + "::defaultExport" in call_targets
    assert str((tmp_path / "module-b.js").resolve()) + "::name1" in call_targets
    assert str((tmp_path / "module-b.js").resolve()) + "::alias2" in call_targets
    assert str((tmp_path / "module-c.js").resolve()) + "::name3" in call_targets
    assert str((tmp_path / "module-d.js").resolve()) + "::default2" in call_targets
    assert str((tmp_path / "module-d.js").resolve()) + "::name4" in call_targets


def test_ts_import_parsing(tmp_path):
    parser = CodeParser()

    (tmp_path / "types.ts").write_text("")
    (tmp_path / "more-types.ts").write_text("")

    ts_file = tmp_path / "test.ts"
    ts_file.write_text("""
import { TypeA } from './types';
import type { TypeB } from './more-types';

export function test(a, b) {
    TypeA(a);
    TypeB(b);
}
""")
    nodes, edges = parser.parse_file(ts_file)
    calls = [e for e in edges if e.kind == "CALLS"]
    call_targets = {e.target for e in calls}

    assert str((tmp_path / "types.ts").resolve()) + "::TypeA" in call_targets
    assert str((tmp_path / "more-types.ts").resolve()) + "::TypeB" in call_targets
