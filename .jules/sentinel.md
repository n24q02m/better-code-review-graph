## 2024-05-24 - [Fix XXE vulnerability in Java dependency resolver]
**Vulnerability:** Found a potential XML External Entity (XXE) vulnerability in `src/better_code_review_graph/resolver/java.py`. The standard library `xml.etree.ElementTree` was used to parse `pom.xml` files, which is vulnerable to XXE injection if malicious XML is provided.
**Learning:** The use of standard library XML parsers is inherently unsafe for untrusted input. The project lacked the safe `defusedxml` dependency to securely handle XML files.
**Prevention:** Always use `defusedxml.ElementTree` when parsing XML from external sources. Do not fall back to the standard library parser, as it fails-open to XXE attacks. Ensure `defusedxml` is a hard dependency in `pyproject.toml`.
