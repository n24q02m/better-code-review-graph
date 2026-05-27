## 2026-05-27 - Fixed TESTED_BY logic and performance
**Learning:** TESTED_BY edges point from the test (source) to the tested function (target). Previous logic added the test (source) to the set of 'tested functions', creating an incorrect set and wasting memory. Additionally, adding both source and target doubled the memory overhead for set insertions without reason.
**Action:** Use `e.target_qualified` exclusively for TESTED_BY relations when identifying the function being tested, which both fixes the semantic logic and reduces the set size by half.
