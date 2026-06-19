# CHANGELOG

<!-- version list -->

## v3.18.0-beta.8 (2026-06-19)

### Bug Fixes

- Bump mcp-core floor to 1.18.0b14 for the key-rotation primitive
  ([`fd88d4f`](https://github.com/n24q02m/better-code-review-graph/commit/fd88d4f1bcd0a6a6769840e2a0885a2220307a49))


## v3.18.0-beta.7 (2026-06-19)

### Features

- DISABLE_LOCAL_EMBED disable-local toggle for embedding
  ([#734](https://github.com/n24q02m/better-code-review-graph/pull/734),
  [`b00b834`](https://github.com/n24q02m/better-code-review-graph/commit/b00b8344ab8b9f7b96a72273d666a6eb13f77922))


## v3.18.0-beta.6 (2026-06-15)

### Bug Fixes

- Clarify embedding-model switch requires reindex (B2 guard)
  ([#709](https://github.com/n24q02m/better-code-review-graph/pull/709),
  [`e39ed42`](https://github.com/n24q02m/better-code-review-graph/commit/e39ed42e1901b4ff5b391d828855f50b5fe99134))

- Correct relay/storage docs to match OAuth-form setup and PerPluginStore
  ([`1c044d7`](https://github.com/n24q02m/better-code-review-graph/commit/1c044d7c175f8e24f94402f0e3f5166f83428da1))

- Stop flaky model download in CI
  ([`5bbcb6b`](https://github.com/n24q02m/better-code-review-graph/commit/5bbcb6b13b49972b2eda20ae5d7779671bbdc637))


## v3.18.0-beta.5 (2026-06-13)

### Bug Fixes

- Bump deps and stop Renovate raising the semgrep floor
  ([#708](https://github.com/n24q02m/better-code-review-graph/pull/708),
  [`31c9f50`](https://github.com/n24q02m/better-code-review-graph/commit/31c9f50d6cba064991071f2accf306673a36e074))

- Config status hangs on Windows under stdio
  ([#705](https://github.com/n24q02m/better-code-review-graph/pull/705),
  [`ef38e43`](https://github.com/n24q02m/better-code-review-graph/commit/ef38e43a924ddd6f3443dd160d8bd72b99e9f8c5))

- Graph build slow on Windows under stdio (git subprocess stall)
  ([#707](https://github.com/n24q02m/better-code-review-graph/pull/707),
  [`a0dca19`](https://github.com/n24q02m/better-code-review-graph/commit/a0dca198c4062ede7b4e3efdf42cba3643b7dedc))

- Local ONNX embed hangs on Windows under stdio
  ([#706](https://github.com/n24q02m/better-code-review-graph/pull/706),
  [`aafa6fe`](https://github.com/n24q02m/better-code-review-graph/commit/aafa6febc6b3ae362e8b8aa992a5a7ea6fa2ef1a))

- Remove literal v<auto> placeholder from stabilization note
  ([#698](https://github.com/n24q02m/better-code-review-graph/pull/698),
  [`8ddf9cc`](https://github.com/n24q02m/better-code-review-graph/commit/8ddf9cc98b93a6cbe72e49898e63b50c4f7d7e08))

- Sync README tagline to current capability description
  ([#700](https://github.com/n24q02m/better-code-review-graph/pull/700),
  [`b587687`](https://github.com/n24q02m/better-code-review-graph/commit/b587687ee5027785f013d7c972fb60d89deebd15))

### Chores

- **deps**: Lock file maintenance
  ([#704](https://github.com/n24q02m/better-code-review-graph/pull/704),
  [`e7af10e`](https://github.com/n24q02m/better-code-review-graph/commit/e7af10e47f2ecbc3d649ecdb3db93d25f4407251))

- **deps**: Update python:3.13-slim-bookworm docker digest to 05b9539
  ([#702](https://github.com/n24q02m/better-code-review-graph/pull/702),
  [`ad0b213`](https://github.com/n24q02m/better-code-review-graph/commit/ad0b213876450ab27859c3851355dcf123988e60))

### Features

- Sync cross-promo section ([#701](https://github.com/n24q02m/better-code-review-graph/pull/701),
  [`1994678`](https://github.com/n24q02m/better-code-review-graph/commit/1994678e1405c93f2018a2685deec80cc9610784))


## v3.18.0-beta.4 (2026-06-12)

### Bug Fixes

- Correct summarize docstring, embedding-only manifest, and 3-pillar desc
  ([#696](https://github.com/n24q02m/better-code-review-graph/pull/696),
  [`34845c9`](https://github.com/n24q02m/better-code-review-graph/commit/34845c9f05b658eedb6484ac116dc865676fd9b4))

- Filter crg vector search by active provider to prevent cross-provider mixing
  ([#697](https://github.com/n24q02m/better-code-review-graph/pull/697),
  [`9d644f4`](https://github.com/n24q02m/better-code-review-graph/commit/9d644f4c2c6b073b0fc8fceaefcbb9f8ab1355d8))

- Pin semgrep <1.162 in renovate to stop re-proposing the mcp-conflict bump (#684)
  ([#693](https://github.com/n24q02m/better-code-review-graph/pull/693),
  [`9805e57`](https://github.com/n24q02m/better-code-review-graph/commit/9805e57e5e46ce974fabebc7146c164ce931b5c9))

- Prevent argument injection in Semgrep wrapper
  ([#687](https://github.com/n24q02m/better-code-review-graph/pull/687),
  [`85e247c`](https://github.com/n24q02m/better-code-review-graph/commit/85e247c569ca94770def1d40d95ad4cd622764e6))

- Remove orphaned Qodo pr-agent config
  ([#694](https://github.com/n24q02m/better-code-review-graph/pull/694),
  [`5062546`](https://github.com/n24q02m/better-code-review-graph/commit/506254649fc26f3b4036127d226bb70b1b0664e9))

- Remove stray plan.md artifact accidentally merged via #686
  ([#692](https://github.com/n24q02m/better-code-review-graph/pull/692),
  [`5cc4cbd`](https://github.com/n24q02m/better-code-review-graph/commit/5cc4cbd9b46c82ab159df014cc8abe4fd3894c82))

- Restore PSR changelog generation and backfill version history
  ([#695](https://github.com/n24q02m/better-code-review-graph/pull/695),
  [`e83f437`](https://github.com/n24q02m/better-code-review-graph/commit/e83f437074af25593777a89be11480d9477a57f0))

### Chores

- **deps**: Lock file maintenance
  ([#685](https://github.com/n24q02m/better-code-review-graph/pull/685),
  [`e9326f0`](https://github.com/n24q02m/better-code-review-graph/commit/e9326f05a02064f779b20b6ee693eb7a038573c4))

### Performance Improvements

- Replace .fetchall() with direct cursor iteration
  ([#686](https://github.com/n24q02m/better-code-review-graph/pull/686),
  [`8a300fe`](https://github.com/n24q02m/better-code-review-graph/commit/8a300fe3fcd5ec2642374c9e626982db8bf3f76a))


## v3.18.0-beta.3 (2026-06-11)

### Bug Fixes

- Document per-task model chains + provider->key table (drop priority-router docs)
  ([#690](https://github.com/n24q02m/better-code-review-graph/pull/690),
  [`00832a6`](https://github.com/n24q02m/better-code-review-graph/commit/00832a68670029a87b23e41014796b7e246917eb))

### Features

- Drop config(action="models") catalog-listing tool action
  ([#691](https://github.com/n24q02m/better-code-review-graph/pull/691),
  [`3220b3e`](https://github.com/n24q02m/better-code-review-graph/commit/3220b3e385dd1fabe46a6ab09341e351ba900d47))


## v3.18.0-beta.2 (2026-06-11)

### Features

- Crg per-task model chains + relay model-chain widget, drop priority-router
  ([#689](https://github.com/n24q02m/better-code-review-graph/pull/689),
  [`430efa0`](https://github.com/n24q02m/better-code-review-graph/commit/430efa024d02ba2dff28451c4101b7df68564894))


## v3.18.0-beta.1 (2026-06-11)

### Bug Fixes

- Drop env api_key when SUMMARY_MODEL overrides provider
  ([#688](https://github.com/n24q02m/better-code-review-graph/pull/688),
  [`b6deb0f`](https://github.com/n24q02m/better-code-review-graph/commit/b6deb0fd71c9100658db4250ca678cff3f129bc2))

- Floor litellm>=1.88.0 to clear proxy-server advisories
  ([#688](https://github.com/n24q02m/better-code-review-graph/pull/688),
  [`b6deb0f`](https://github.com/n24q02m/better-code-review-graph/commit/b6deb0fd71c9100658db4250ca678cff3f129bc2))

### Features

- Migrate embedding + summarizer dispatch to litellm passthrough via mcp-core[llm]
  ([#688](https://github.com/n24q02m/better-code-review-graph/pull/688),
  [`b6deb0f`](https://github.com/n24q02m/better-code-review-graph/commit/b6deb0fd71c9100658db4250ca678cff3f129bc2))

- Migrate embedding + summarizer dispatch to mcp_core.llm litellm passthrough
  ([#688](https://github.com/n24q02m/better-code-review-graph/pull/688),
  [`b6deb0f`](https://github.com/n24q02m/better-code-review-graph/commit/b6deb0fd71c9100658db4250ca678cff3f129bc2))


## v3.17.2-beta.2 (2026-06-10)

### Bug Fixes

- Handle non-dict payload in live integration tests
  ([#663](https://github.com/n24q02m/better-code-review-graph/pull/663),
  [`84b464e`](https://github.com/n24q02m/better-code-review-graph/commit/84b464e70915b60cafa35a2e9754fd39fa203e4b))

- Remove forced stale module-level state and refresh state in setup_status
  ([#668](https://github.com/n24q02m/better-code-review-graph/pull/668),
  [`1018800`](https://github.com/n24q02m/better-code-review-graph/commit/1018800447dcb55bcfa686a053044c4a4df92091))

- Remove unused check_available method from embedding backends
  ([#682](https://github.com/n24q02m/better-code-review-graph/pull/682),
  [`d6e68f5`](https://github.com/n24q02m/better-code-review-graph/commit/d6e68f5c53ce29b641124b32d588010a79796372))

- Replace flaky wall-clock N+1 perf assertion with query count
  ([#683](https://github.com/n24q02m/better-code-review-graph/pull/683),
  [`6b6b8d6`](https://github.com/n24q02m/better-code-review-graph/commit/6b6b8d6a6f7386b081f068cf199ed1ab083212ec))

- Resolve historical bug in path resolution and mock embeddings in tests
  ([#670](https://github.com/n24q02m/better-code-review-graph/pull/670),
  [`2b30533`](https://github.com/n24q02m/better-code-review-graph/commit/2b30533e091d9afc54c4e3102f35568d8628db16))

- Resolve historical bug in path resolution for bundled resources
  ([#670](https://github.com/n24q02m/better-code-review-graph/pull/670),
  [`2b30533`](https://github.com/n24q02m/better-code-review-graph/commit/2b30533e091d9afc54c4e3102f35568d8628db16))

- Resolve historical path resolution bug and improve embedding tests reliability
  ([#670](https://github.com/n24q02m/better-code-review-graph/pull/670),
  [`2b30533`](https://github.com/n24q02m/better-code-review-graph/commit/2b30533e091d9afc54c4e3102f35568d8628db16))

- Resolve historical path resolution bug and mock embeddings in tests
  ([#670](https://github.com/n24q02m/better-code-review-graph/pull/670),
  [`2b30533`](https://github.com/n24q02m/better-code-review-graph/commit/2b30533e091d9afc54c4e3102f35568d8628db16))

### Refactoring

- Break down query_graph into modular helper functions
  ([#672](https://github.com/n24q02m/better-code-review-graph/pull/672),
  [`c1c3c7c`](https://github.com/n24q02m/better-code-review-graph/commit/c1c3c7c0157005824bf099789603dbdba21a0219))

### Testing

- Add comprehensive coverage for temporal.py
  ([#675](https://github.com/n24q02m/better-code-review-graph/pull/675),
  [`7d0944e`](https://github.com/n24q02m/better-code-review-graph/commit/7d0944e2ed7f11610e17dd3df79606a47ad2dfa6))

- Add coverage for GraphStore.get_all_nodes
  ([#667](https://github.com/n24q02m/better-code-review-graph/pull/667),
  [`56f44d4`](https://github.com/n24q02m/better-code-review-graph/commit/56f44d42097cab8db9accec66dd5474fc1b352d1))

- Add coverage for search_edges_by_target_names
  ([#665](https://github.com/n24q02m/better-code-review-graph/pull/665),
  [`e91cf2a`](https://github.com/n24q02m/better-code-review-graph/commit/e91cf2acddeeb27845fa6e72908485301637f626))

- Reorganize and consolidate relay_setup tests
  ([#673](https://github.com/n24q02m/better-code-review-graph/pull/673),
  [`abce684`](https://github.com/n24q02m/better-code-review-graph/commit/abce6840c804c113d5fe7d621ea2564c8cff7f03))


## v3.17.2-beta.1 (2026-06-10)

### Bug Fixes

- Add Comparison section to README capability matrix
  ([#662](https://github.com/n24q02m/better-code-review-graph/pull/662),
  [`dcb08cd`](https://github.com/n24q02m/better-code-review-graph/commit/dcb08cd437a953dbc52b1a82428f1e134e40e143))

- Correct docs drift in tool count, semgrep rules, help topics, dead links
  ([#661](https://github.com/n24q02m/better-code-review-graph/pull/661),
  [`cdb4232`](https://github.com/n24q02m/better-code-review-graph/commit/cdb4232dd0c00ff871a0d027f6f4b0eca774873e))

### Chores

- **deps**: Lock file maintenance
  ([#659](https://github.com/n24q02m/better-code-review-graph/pull/659),
  [`9e5b7f0`](https://github.com/n24q02m/better-code-review-graph/commit/9e5b7f0b38482f5d6d745c48b51af892ec52396a))

- **deps**: Update step-security/harden-runner digest to 9af89fc
  ([#657](https://github.com/n24q02m/better-code-review-graph/pull/657),
  [`c6e35b4`](https://github.com/n24q02m/better-code-review-graph/commit/c6e35b4306ef25cafbcc43008ee17fb36c970fe9))


## v3.17.1 (2026-06-09)


## v3.17.1-beta.1 (2026-06-09)

### Bug Fixes

- Gitignore bot/merge junk artifacts (*.orig/*.rej/*.patch/*.diff/*.cover/*.bak)
  ([#627](https://github.com/n24q02m/better-code-review-graph/pull/627),
  [`30ea5d5`](https://github.com/n24q02m/better-code-review-graph/commit/30ea5d56effdbab87e7aba42faec9cc3bbae89b5))

### Chores

- **deps**: Lock file maintenance
  ([#631](https://github.com/n24q02m/better-code-review-graph/pull/631),
  [`1900f3b`](https://github.com/n24q02m/better-code-review-graph/commit/1900f3b40fb800d41129b2158b122bc27cb7eaad))

- **deps**: Update codecov/codecov-action action to v7
  ([#630](https://github.com/n24q02m/better-code-review-graph/pull/630),
  [`f19d46f`](https://github.com/n24q02m/better-code-review-graph/commit/f19d46f44420076b2ce6f05094672cababff4e79))


## v3.17.0 (2026-06-07)

### Bug Fixes

- Cover dev-version fallback via _resolve_version helper and update existing test
  ([#624](https://github.com/n24q02m/better-code-review-graph/pull/624),
  [`d366e41`](https://github.com/n24q02m/better-code-review-graph/commit/d366e41c291a48cc5262b9b95e12e65edc16196c))

- Report package version in serverInfo instead of fastmcp version
  ([#624](https://github.com/n24q02m/better-code-review-graph/pull/624),
  [`d366e41`](https://github.com/n24q02m/better-code-review-graph/commit/d366e41c291a48cc5262b9b95e12e65edc16196c))


## v3.17.0-beta.1 (2026-06-07)

### Bug Fixes

- Harden git subprocess calls against argument injection
  ([`fb33ce8`](https://github.com/n24q02m/better-code-review-graph/commit/fb33ce8dbd0c23d7de9d30c37147043b3b9185be))

- Prevent bare-name fallback pulling wrong edges in importers_of and tests_for
  ([`864757c`](https://github.com/n24q02m/better-code-review-graph/commit/864757cb3d0e13d87583e0536b434884277a8748))

- Prevent path traversal in export_graph_dispatch output_path
  ([`5f91325`](https://github.com/n24q02m/better-code-review-graph/commit/5f9132502ddb64b4cfc890ee30ac15aa1d5c92ba))

- Remove unused SupportedLanguage import in parser
  ([`452f940`](https://github.com/n24q02m/better-code-review-graph/commit/452f940228d8343a7d2ada93ee3c389f8d195296))

- Update actions/checkout digest to df4cb1c
  ([`548d4c5`](https://github.com/n24q02m/better-code-review-graph/commit/548d4c580ff2c33e82fd7ba12a2e7b2307ba530c))

- Update github/codeql-action digest to dd903d2
  ([`ad417df`](https://github.com/n24q02m/better-code-review-graph/commit/ad417df4a0727fa7fdd0ba7cf22306297f2df141))

### Features

- Add coverage tests for _handle_not_found
  ([`78fc047`](https://github.com/n24q02m/better-code-review-graph/commit/78fc04785e8d23c1e1ded52563f1a0a6677bf9d4))

- Add exception coverage test for parse_bytes in renamed_in_diff
  ([`e223694`](https://github.com/n24q02m/better-code-review-graph/commit/e22369475dbd5b1fdcb44cb85a9fe38b6d94a94e))

- Add OSError coverage test for renamed_in_diff path resolution
  ([`a317dd9`](https://github.com/n24q02m/better-code-review-graph/commit/a317dd9200007e499e7e78508b2fc4c26cc24112))

- Add OSError coverage tests for get_review_context and spot_check
  ([`cd99df0`](https://github.com/n24q02m/better-code-review-graph/commit/cd99df04e324f0bc0205aaf7033d61d8d49194f1))

- Add path resolution fallback coverage tests
  ([`48a98a0`](https://github.com/n24q02m/better-code-review-graph/commit/48a98a066bbaa6d14a5b9a62f3b7bce9593c2387))

- Add unit tests for _estimate_payload_bytes
  ([`717ce7f`](https://github.com/n24q02m/better-code-review-graph/commit/717ce7f188aa9345f80d219331cf85dae43bfd6a))

- Add unit tests for _lookup_node_directly
  ([`59b20fb`](https://github.com/n24q02m/better-code-review-graph/commit/59b20fb8e0f1ad288088f54ee071ded836338ecf))

- Add unit tests for _resolve_search_candidates
  ([`a160075`](https://github.com/n24q02m/better-code-review-graph/commit/a160075ba9401fc50802053f381f76e5bb9699cb))

- Add unit tests for _semgrep_executable helper
  ([`d8671a2`](https://github.com/n24q02m/better-code-review-graph/commit/d8671a20ca890d91e36d6e2115e62f54842782da))


## v3.16.4 (2026-06-01)

### Bug Fixes

- Pin mcp-core 1.17.2 (stable)
  ([`20b04bc`](https://github.com/n24q02m/better-code-review-graph/commit/20b04bcf62488a17b093ed41beb40c855b34c476))


## v3.16.4-beta.1 (2026-06-01)

### Bug Fixes

- Bump mcp-core to 1.17.2-beta.1 for beta testing
  ([`dc12a55`](https://github.com/n24q02m/better-code-review-graph/commit/dc12a5589cdc458855659520959f3751aacdf263))

- Repoint dead docs/setup-manual.md link to hosted setup guide
  ([#551](https://github.com/n24q02m/better-code-review-graph/pull/551),
  [`23bdcf1`](https://github.com/n24q02m/better-code-review-graph/commit/23bdcf175f31dd8bc96f58d87cbd3f385664799e))

- Sync docs to actual 6-tool surface and config/help actions
  ([#550](https://github.com/n24q02m/better-code-review-graph/pull/550),
  [`feb1a11`](https://github.com/n24q02m/better-code-review-graph/commit/feb1a115db57fa56df2012cdeb3004f97f201deb))

- Use defusedxml to prevent XXE in XML parsing
  ([#546](https://github.com/n24q02m/better-code-review-graph/pull/546),
  [`c7c0678`](https://github.com/n24q02m/better-code-review-graph/commit/c7c0678935a4423c3707aa3fde50bdfa5c864be7))


## v3.16.3 (2026-05-29)

### Bug Fixes

- Pin mcp-core 1.17.1 (BearerMCPApp resource_metadata #260)
  ([`24edb45`](https://github.com/n24q02m/better-code-review-graph/commit/24edb45bd641b3a08d8d23eb89b3f94eebaf12da))


## v3.16.2 (2026-05-29)

### Bug Fixes

- Pin mcp-core 1.17.0 (stable OAuth refresh_token)
  ([`f201731`](https://github.com/n24q02m/better-code-review-graph/commit/f2017310b045cea9ea6d760a57685a77e7583eb2))


## v3.16.2-beta.1 (2026-05-29)

### Bug Fixes

- Add get_review_context no-diff edge case tests
  ([#528](https://github.com/n24q02m/better-code-review-graph/pull/528),
  [`5894c24`](https://github.com/n24q02m/better-code-review-graph/commit/5894c246b76c89bd7abf50bb26741a7503282b9e))

- Add list_graph_stats coverage tests
  ([#524](https://github.com/n24q02m/better-code-review-graph/pull/524),
  [`ab9a319`](https://github.com/n24q02m/better-code-review-graph/commit/ab9a31980a8ab82183217f0e80a5d071c24adb4d))

- Bump mcp-core to 1.17.0-beta.1 for OAuth refresh_token
  ([`9fccdd0`](https://github.com/n24q02m/better-code-review-graph/commit/9fccdd034973cc5246d96f826dde23b4ad42e874))

- Correct stale tool names in SessionStart hook guidance
  ([#539](https://github.com/n24q02m/better-code-review-graph/pull/539),
  [`9cfb922`](https://github.com/n24q02m/better-code-review-graph/commit/9cfb92249f31ff11611c897ab5a44a27b9351c49))

- Prevent SQL injection in alter table column execution
  ([#520](https://github.com/n24q02m/better-code-review-graph/pull/520),
  [`9d9da03`](https://github.com/n24q02m/better-code-review-graph/commit/9d9da035c0b8aeef610a3af6ce16ddb7b5664634))

- Prevent SQL injection in temporal table creation
  ([#523](https://github.com/n24q02m/better-code-review-graph/pull/523),
  [`a40f8f3`](https://github.com/n24q02m/better-code-review-graph/commit/a40f8f3d093fe0cb5f1945942e9e72c94b5d41e3))

### Testing

- Add unit tests for list_graph_stats tool
  ([#524](https://github.com/n24q02m/better-code-review-graph/pull/524),
  [`ab9a319`](https://github.com/n24q02m/better-code-review-graph/commit/ab9a31980a8ab82183217f0e80a5d071c24adb4d))


## v3.16.1 (2026-05-28)

### Bug Fixes

- Drop local path source for mcp-core to align with PyPI-only pattern
  ([`6c2664d`](https://github.com/n24q02m/better-code-review-graph/commit/6c2664d63aa3b97d969662e31d47a3a16a450cad))

- Resolve ty 0.0.40 type errors and align list_kinds test with cursor iteration
  ([`6154f08`](https://github.com/n24q02m/better-code-review-graph/commit/6154f08cb7a3fb19933ca04394a4ab0fa1f32d81))

- Ruff format graph.py and tools.py to satisfy CI
  ([`a0e44df`](https://github.com/n24q02m/better-code-review-graph/commit/a0e44df134caba79f571ca26b9d1916485692008))


## v3.16.1-beta.1 (2026-05-28)

### Bug Fixes

- **deps**: Cap semgrep to <1.162 to avoid mcp==1.23.3 transitive pin conflict
  ([`f29b5a0`](https://github.com/n24q02m/better-code-review-graph/commit/f29b5a0fcc6b7d5e367e72796803a91a91669986))

- **deps**: Update non-major dependencies
  ([#513](https://github.com/n24q02m/better-code-review-graph/pull/513),
  [`c33936d`](https://github.com/n24q02m/better-code-review-graph/commit/c33936d2d7620f4dc75949acb974485a6d10f3b3))

### Performance Improvements

- Replace fetchall() with direct cursor iteration
  ([#514](https://github.com/n24q02m/better-code-review-graph/pull/514),
  [`c9741ab`](https://github.com/n24q02m/better-code-review-graph/commit/c9741ab43a16733dcc2653f1e8f3a44f33cbf55d))


## v3.16.0 (2026-05-26)

### Bug Fixes

- **deps**: Update dependency cohere to v7
  ([#509](https://github.com/n24q02m/better-code-review-graph/pull/509),
  [`0209d0d`](https://github.com/n24q02m/better-code-review-graph/commit/0209d0de01080e0f938fb47368ac86dfa1d65d4b))

### Chores

- **deps**: Update github/codeql-action digest to 03e4368
  ([#504](https://github.com/n24q02m/better-code-review-graph/pull/504),
  [`8c3c19a`](https://github.com/n24q02m/better-code-review-graph/commit/8c3c19aaa6d27afd2281bd41b2d091c073a8cbc6))

- **deps**: Update python:3.13-slim-bookworm docker digest to e4fa1f9
  ([#505](https://github.com/n24q02m/better-code-review-graph/pull/505),
  [`b968a27`](https://github.com/n24q02m/better-code-review-graph/commit/b968a27490eecae08876cf452d8ac34b5b400e19))


## v3.16.0-beta.4 (2026-05-24)

### Bug Fixes

- **deps**: Regenerate uv.lock with UV_NO_SOURCES for Docker compatibility
  ([`183fa97`](https://github.com/n24q02m/better-code-review-graph/commit/183fa97508d2dec5a8737ee260d98a0f37016f35))


## v3.16.0-beta.3 (2026-05-24)

### Bug Fixes

- Optimize SQLite kind filter, batch checks, harden security
  ([#496](https://github.com/n24q02m/better-code-review-graph/pull/496),
  [`483d1ce`](https://github.com/n24q02m/better-code-review-graph/commit/483d1ce318168c048abe9d2f5f641b98d6d0d45c))

- **deps**: Bump urllib3 to 2.7.0 + idna to 3.16 (Dependabot security alerts)
  ([`eb4655d`](https://github.com/n24q02m/better-code-review-graph/commit/eb4655df4c2aa74c64fa68aabb670b307d8f5388))

- **deps**: Update dependency google-genai to v2
  ([#485](https://github.com/n24q02m/better-code-review-graph/pull/485),
  [`948449f`](https://github.com/n24q02m/better-code-review-graph/commit/948449fdb447f6ede4ba276193b6c3bbdf559c51))

### Chores

- **deps**: Bump runtime + workflow pins from open Renovate PRs
  ([#496](https://github.com/n24q02m/better-code-review-graph/pull/496),
  [`483d1ce`](https://github.com/n24q02m/better-code-review-graph/commit/483d1ce318168c048abe9d2f5f641b98d6d0d45c))

- **deps**: Update actions/create-github-app-token digest to bcd2ba4
  ([#487](https://github.com/n24q02m/better-code-review-graph/pull/487),
  [`0166188`](https://github.com/n24q02m/better-code-review-graph/commit/01661888cb140aeee8e72b30efc380ca0f6f35ea))

- **deps**: Update codecov/codecov-action digest to e79a696
  ([#497](https://github.com/n24q02m/better-code-review-graph/pull/497),
  [`e89384e`](https://github.com/n24q02m/better-code-review-graph/commit/e89384ee48844dfcd11c3b6ce76541236c161354))

- **deps**: Update docker/build-push-action digest to f9f3042
  ([#498](https://github.com/n24q02m/better-code-review-graph/pull/498),
  [`a6a221e`](https://github.com/n24q02m/better-code-review-graph/commit/a6a221e0c5fa14e692b1b3b65e9ef17c32f0b7a2))

- **deps**: Update docker/login-action digest to 650006c
  ([#499](https://github.com/n24q02m/better-code-review-graph/pull/499),
  [`673408f`](https://github.com/n24q02m/better-code-review-graph/commit/673408f9797809ffb7e74f639e71f7f841bbfaa8))

- **deps**: Update docker/setup-buildx-action digest to d7f5e7f
  ([#502](https://github.com/n24q02m/better-code-review-graph/pull/502),
  [`c871a77`](https://github.com/n24q02m/better-code-review-graph/commit/c871a77fff8074ed77e74e3cc983c77dc0b0aeab))

- **deps**: Update github/codeql-action digest to 458d36d
  ([#489](https://github.com/n24q02m/better-code-review-graph/pull/489),
  [`e6c48df`](https://github.com/n24q02m/better-code-review-graph/commit/e6c48df8bc8aa34e45415624a2c92f426e2532a0))

- **deps**: Update step-security/harden-runner digest to ab7a940
  ([#490](https://github.com/n24q02m/better-code-review-graph/pull/490),
  [`09aa29c`](https://github.com/n24q02m/better-code-review-graph/commit/09aa29c455344913ceb0a62909ccfd26a028ddbd))

### Performance Improvements

- **graph**: Push edge kind filter into SQLite + batch repo/survival lookups
  ([#496](https://github.com/n24q02m/better-code-review-graph/pull/496),
  [`483d1ce`](https://github.com/n24q02m/better-code-review-graph/commit/483d1ce318168c048abe9d2f5f641b98d6d0d45c))

### Testing

- Cover kind filter, batched lookups, security_scan batching
  ([#496](https://github.com/n24q02m/better-code-review-graph/pull/496),
  [`483d1ce`](https://github.com/n24q02m/better-code-review-graph/commit/483d1ce318168c048abe9d2f5f641b98d6d0d45c))


## v3.16.0-beta.2 (2026-05-10)

### Bug Fixes

- Copy migrations/ + rules/ into Docker builder for Hatch force-include
  ([#482](https://github.com/n24q02m/better-code-review-graph/pull/482),
  [`5ee20be`](https://github.com/n24q02m/better-code-review-graph/commit/5ee20bebf1bb61e7c05bece87aa492f8620f3a96))


## v3.16.0-beta.1 (2026-05-10)

### Bug Fixes

- Bump python-multipart to 0.0.27 to patch CVE-2026-42561 (DoS via unbounded multipart headers)
  ([#452](https://github.com/n24q02m/better-code-review-graph/pull/452),
  [`e831beb`](https://github.com/n24q02m/better-code-review-graph/commit/e831beb741d33a077447bd7b67ef01c87ae4eaf1))

- Document cross-repo federation in help topics
  ([#464](https://github.com/n24q02m/better-code-review-graph/pull/464),
  [`e803603`](https://github.com/n24q02m/better-code-review-graph/commit/e80360353ee3b757dd3d47b54c03605e65343f77))

- Document security tool + temporal tracking + breaking migration
  ([#480](https://github.com/n24q02m/better-code-review-graph/pull/480),
  [`70dde4e`](https://github.com/n24q02m/better-code-review-graph/commit/70dde4e0cf3d48e0051fc8b3c243796f97b5649a))

- Forward target_repos in federated build + 3-repo smoke fixture
  ([#469](https://github.com/n24q02m/better-code-review-graph/pull/469),
  [`aa70484`](https://github.com/n24q02m/better-code-review-graph/commit/aa7048407cb5c7b882776a7553763f0e30cc9130))

- Harden alembic resolver + tests for installed-mode + future-revision + parity gates
  ([#453](https://github.com/n24q02m/better-code-review-graph/pull/453),
  [`bd23e90`](https://github.com/n24q02m/better-code-review-graph/commit/bd23e90bcd8f063f9eddbfe5b5ee8c397c38dba0))

- Pre-2.0 release smoke + breaking-change announcement banner
  ([#481](https://github.com/n24q02m/better-code-review-graph/pull/481),
  [`2b9e97b`](https://github.com/n24q02m/better-code-review-graph/commit/2b9e97b869c12dbce09e83b62ed17394821cdd45))

- Regenerate uv.lock without [tool.uv.sources] directory pin
  ([#472](https://github.com/n24q02m/better-code-review-graph/pull/472),
  [`57a77eb`](https://github.com/n24q02m/better-code-review-graph/commit/57a77eb8b369133b34f139072b5cbd559ffcb175))

- Regenerate uv.lock without directory pin (Task 4)
  ([#473](https://github.com/n24q02m/better-code-review-graph/pull/473),
  [`1f399cc`](https://github.com/n24q02m/better-code-review-graph/commit/1f399cc95953118452cde2255501fd5961a8664b))

- Regex in 005_temporal_columns must consume exactly 3 slashes
  ([#475](https://github.com/n24q02m/better-code-review-graph/pull/475),
  [`3a44f1d`](https://github.com/n24q02m/better-code-review-graph/commit/3a44f1d6c340682070eaaced8f5525438728d409))

- **deps**: Update dependency google-genai to v2
  ([#468](https://github.com/n24q02m/better-code-review-graph/pull/468),
  [`ab08f4d`](https://github.com/n24q02m/better-code-review-graph/commit/ab08f4dfaf53822a907a40232cfe665e954cd653))

### Chores

- **deps**: Update actions/dependency-review-action action to v5
  ([#467](https://github.com/n24q02m/better-code-review-graph/pull/467),
  [`e96a9d1`](https://github.com/n24q02m/better-code-review-graph/commit/e96a9d1e1cc40649135a63f332acfff992843762))

- **deps**: Update github/codeql-action digest to 7fd177f
  ([#451](https://github.com/n24q02m/better-code-review-graph/pull/451),
  [`864fe77`](https://github.com/n24q02m/better-code-review-graph/commit/864fe772e3efb57b133588af2284965b7dc65591))

- **deps**: Update python:3.13-slim-bookworm docker digest to 386df64
  ([#465](https://github.com/n24q02m/better-code-review-graph/pull/465),
  [`0da0ff1`](https://github.com/n24q02m/better-code-review-graph/commit/0da0ff158a1390598e3a6912230822431f1f2e90))

### Features

- Alembic 003_federation — add repo_id + repos table for cross-repo scoping
  ([#454](https://github.com/n24q02m/better-code-review-graph/pull/454),
  [`c1c7bd8`](https://github.com/n24q02m/better-code-review-graph/commit/c1c7bd8b2060ff23a7671097a26797cfb444a421))

- Alembic 004_security_tags — add nullable security_tags JSON column
  ([#471](https://github.com/n24q02m/better-code-review-graph/pull/471),
  [`004355b`](https://github.com/n24q02m/better-code-review-graph/commit/004355babe8923e135da6f37cdfe2e130c045831))

- Alembic 005_temporal_columns — BREAKING add valid_from_sha/valid_to_sha
  ([#475](https://github.com/n24q02m/better-code-review-graph/pull/475),
  [`3a44f1d`](https://github.com/n24q02m/better-code-review-graph/commit/3a44f1d6c340682070eaaced8f5525438728d409))

- Alembic 006_commits_table + first-parent backfill
  ([#476](https://github.com/n24q02m/better-code-review-graph/pull/476),
  [`9d824f0`](https://github.com/n24q02m/better-code-review-graph/commit/9d824f04dfd12216de8e1c148ab65125310afdca))

- Alembic baseline + Phase 1 summary columns recorded as 001_baseline + 002_summary_columns
  ([#453](https://github.com/n24q02m/better-code-review-graph/pull/453),
  [`bd23e90`](https://github.com/n24q02m/better-code-review-graph/commit/bd23e90bcd8f063f9eddbfe5b5ee8c397c38dba0))

- As_of + diff cross-cutting params on query + review
  ([#478](https://github.com/n24q02m/better-code-review-graph/pull/478),
  [`ec0d059`](https://github.com/n24q02m/better-code-review-graph/commit/ec0d05941044d961fae4d4de8008da146bcb4ea0))

- Backup graph.db to .pre-2.0.bak before BREAKING 005_temporal_columns migration
  ([#470](https://github.com/n24q02m/better-code-review-graph/pull/470),
  [`e4ee8b9`](https://github.com/n24q02m/better-code-review-graph/commit/e4ee8b9105172372fc8361bc2aa0674aecb8e7c4))

- Cross-cutting repo param on query + review actions
  ([#463](https://github.com/n24q02m/better-code-review-graph/pull/463),
  [`093101b`](https://github.com/n24q02m/better-code-review-graph/commit/093101b6d8fa2f98a70c563668e6f1dbd32a59a1))

- Cross-repo resolver dispatcher + fallback for tier-2 languages
  ([#461](https://github.com/n24q02m/better-code-review-graph/pull/461),
  [`a09510c`](https://github.com/n24q02m/better-code-review-graph/commit/a09510cba2e823953cfa55411ccb6fb71bd65e98))

- Go cross-repo resolver -- go.mod replace + go.work workspaces
  ([#458](https://github.com/n24q02m/better-code-review-graph/pull/458),
  [`e5a41d3`](https://github.com/n24q02m/better-code-review-graph/commit/e5a41d3ae8c3f755afc0dc6a75ab676411cff296))

- Java cross-repo resolver -- maven modules + gradle include parsing
  ([#460](https://github.com/n24q02m/better-code-review-graph/pull/460),
  [`5901ca2`](https://github.com/n24q02m/better-code-review-graph/commit/5901ca2140821def70e96037ad06d92fe9e4ae74))

- Parser + incremental — populate repo_id and refresh repos.last_indexed_sha
  ([#462](https://github.com/n24q02m/better-code-review-graph/pull/462),
  [`c8fb4e8`](https://github.com/n24q02m/better-code-review-graph/commit/c8fb4e8acb1b0e3bfd9ff356ad823d8916feb060))

- Phase 2 Task 0 — alembic baseline + Phase 1 summary stamp target
  ([#453](https://github.com/n24q02m/better-code-review-graph/pull/453),
  [`bd23e90`](https://github.com/n24q02m/better-code-review-graph/commit/bd23e90bcd8f063f9eddbfe5b5ee8c397c38dba0))

- Phase 3 Task 3 — tier-1 heuristic security scanner
  ([#472](https://github.com/n24q02m/better-code-review-graph/pull/472),
  [`57a77eb`](https://github.com/n24q02m/better-code-review-graph/commit/57a77eb8b369133b34f139072b5cbd559ffcb175))

- Phase 3 Task 4 — Semgrep tier-2 security engine ([security] extra)
  ([#473](https://github.com/n24q02m/better-code-review-graph/pull/473),
  [`1f399cc`](https://github.com/n24q02m/better-code-review-graph/commit/1f399cc95953118452cde2255501fd5961a8664b))

- Phase 3 Task 6 — alembic 005_temporal_columns BREAKING (valid_from_sha + valid_to_sha)
  ([#475](https://github.com/n24q02m/better-code-review-graph/pull/475),
  [`3a44f1d`](https://github.com/n24q02m/better-code-review-graph/commit/3a44f1d6c340682070eaaced8f5525438728d409))

- Python cross-repo resolver — pyproject.toml deps + namespace package walk
  ([#456](https://github.com/n24q02m/better-code-review-graph/pull/456),
  [`815a1a5`](https://github.com/n24q02m/better-code-review-graph/commit/815a1a5d7150a5471fae51df9456e5228dcc3b4d))

- RepoRegistry path-derived repo_id with deterministic id derivation
  ([#455](https://github.com/n24q02m/better-code-review-graph/pull/455),
  [`9e63050`](https://github.com/n24q02m/better-code-review-graph/commit/9e630505ed0ec7a148cfe1f3e153bcaf209ee288))

- Review.delta show_line_shifts mode for refactor auditing (#320)
  ([#479](https://github.com/n24q02m/better-code-review-graph/pull/479),
  [`989880c`](https://github.com/n24q02m/better-code-review-graph/commit/989880c76434656fe96ffae1589396754b4c1987))

- Rust cross-repo resolver -- Cargo.toml path deps + workspace members
  ([#459](https://github.com/n24q02m/better-code-review-graph/pull/459),
  [`fadaae6`](https://github.com/n24q02m/better-code-review-graph/commit/fadaae65151e1258dcb1fb73eb3b445974b24f17))

- Security MCP tool — scan/report/suppress/rule_list actions
  ([#474](https://github.com/n24q02m/better-code-review-graph/pull/474),
  [`3e347df`](https://github.com/n24q02m/better-code-review-graph/commit/3e347dfad0ef71ad51fb1ea574ca5d4f9138a51d))

- TemporalIndex — close-out + supersede logic for nodes/edges across commits
  ([#477](https://github.com/n24q02m/better-code-review-graph/pull/477),
  [`43ef41d`](https://github.com/n24q02m/better-code-review-graph/commit/43ef41d455d2b1229ecc7ec3b947d3ec56ecd47b))

- Tier-1 heuristic security scanner -- 5 rules covering OWASP top sinks
  ([#472](https://github.com/n24q02m/better-code-review-graph/pull/472),
  [`57a77eb`](https://github.com/n24q02m/better-code-review-graph/commit/57a77eb8b369133b34f139072b5cbd559ffcb175))

- Tier-2 semgrep security engine via [security] extra — opt-in install
  ([#473](https://github.com/n24q02m/better-code-review-graph/pull/473),
  [`1f399cc`](https://github.com/n24q02m/better-code-review-graph/commit/1f399cc95953118452cde2255501fd5961a8664b))

- Typescript cross-repo resolver — tsconfig paths + package.json workspaces
  ([#457](https://github.com/n24q02m/better-code-review-graph/pull/457),
  [`02b3346`](https://github.com/n24q02m/better-code-review-graph/commit/02b3346003ed2f7b66bb189836265f8bb5a10314))


## v3.15.1 (2026-05-09)


## v3.15.1-beta.2 (2026-05-08)

### Bug Fixes

- Regenerate uv.lock without [tool.uv.sources] for Docker build
  ([`de9567d`](https://github.com/n24q02m/better-code-review-graph/commit/de9567d385fc0daf5d16601c3963ff82808aa52d))


## v3.15.1-beta.1 (2026-05-08)

### Bug Fixes

- Ruff import sort + format on incremental.py for CI green
  ([`96a7d17`](https://github.com/n24q02m/better-code-review-graph/commit/96a7d17ebffe00d61520eb946f074045bda7e04e))


## v3.15.0 (2026-05-08)


## v3.15.0-beta.1 (2026-05-08)

### Bug Fixes

- Batch-load callers via WHERE IN to fix N+1 query
  ([`955df3f`](https://github.com/n24q02m/better-code-review-graph/commit/955df3f33ae556f87d3efa20f7dd5cda3fa79f1b))

- Dual-cache _filter_valid_paths for fewer OS resolve calls
  ([`e57bbd1`](https://github.com/n24q02m/better-code-review-graph/commit/e57bbd1900346adf4cbe2f74c66298d617028885))

- Prevent path traversal in _sub_data_dir credential storage
  ([`4039c9f`](https://github.com/n24q02m/better-code-review-graph/commit/4039c9f83cb65801c2366586bff37034522c2383))

- Reduce complexity of _handle_solidity_node via helper extraction
  ([`cf67f74`](https://github.com/n24q02m/better-code-review-graph/commit/cf67f74e75aed341c9146823e13dfe2ac0824ed8))

- Reduce complexity of _resolve_query_target via early returns
  ([`940c36b`](https://github.com/n24q02m/better-code-review-graph/commit/940c36b00ad7fa2d446d30fe99e09ec5fbc11f17))

- Reduce complexity of incremental_update via helper extraction
  ([`3f48caf`](https://github.com/n24q02m/better-code-review-graph/commit/3f48cafeddafec2b8718e18337e1e3ddeb6be14d))

- Remove unused 'from __future__ import annotations' in graph.py
  ([`dc9cef6`](https://github.com/n24q02m/better-code-review-graph/commit/dc9cef6dd4d5fc5cdf6e9dfcff0760637afb6425))

- Remove unused 'from __future__ import annotations' in relay_schema.py
  ([`18e3b75`](https://github.com/n24q02m/better-code-review-graph/commit/18e3b75a72376a21c4575d0950387c603ea15ea5))

- Remove unused 'from __future__ import annotations' in tools.py
  ([`2866cfc`](https://github.com/n24q02m/better-code-review-graph/commit/2866cfc7f835983b555a62b4944f43c2aa7f3995))

- Stream edges from sqlite instead of loading entire table in _build_networkx_graph
  ([`bea89d7`](https://github.com/n24q02m/better-code-review-graph/commit/bea89d7046fdfc1e107745fc940653fabe82690a))

- **deps**: Bump n24q02m-mcp-core to >=1.14.0 + qwen3-embed to >=1.9.2
  ([`634fee2`](https://github.com/n24q02m/better-code-review-graph/commit/634fee26c0e86d9506289171ed16d9db2fceddd9))

### Features

- Add error path test for _list_kinds_in_graph
  ([`966d94a`](https://github.com/n24q02m/better-code-review-graph/commit/966d94aa74629ac2bd9c0048b2770dce4e83dea0))

- Add error path test for get_docs_section store initialization
  ([`778d340`](https://github.com/n24q02m/better-code-review-graph/commit/778d340d6a3fd3629c70ab184dc5c7d121c744b4))

- Add error path test for graph build/update
  ([`89dd791`](https://github.com/n24q02m/better-code-review-graph/commit/89dd791a219bf67d15570d79474e6cd1439fe287))

- Add legacy-DB migration + idempotency tests for summary columns
  ([`d65eddd`](https://github.com/n24q02m/better-code-review-graph/commit/d65eddd79d8d36493ebf82a0779dbf124250f249))

- Add summary/summary_provider/source_hash columns to nodes for Phase 1 LLM summaries
  ([`04b9df9`](https://github.com/n24q02m/better-code-review-graph/commit/04b9df967554a97157261fd27f70b9b4c0faf35a))

- Add Table of contents heading + auto-generated link list (Spec E Wave 2)
  ([`d1133bc`](https://github.com/n24q02m/better-code-review-graph/commit/d1133bc742729ced7cb5cc2cf844d9a8f360d497))

- Add tests for get_nodes_by_files batch fetch
  ([`cfb2fde`](https://github.com/n24q02m/better-code-review-graph/commit/cfb2fde700a72100bbd4de7c79934bf930ed44f9))

- Batch_summarize with source_hash cache + cost cap + per-node error tolerance
  ([`fdc7664`](https://github.com/n24q02m/better-code-review-graph/commit/fdc7664e629c76ba6cf17432eb8254f21b81c62a))

- Close coverage gaps in export_graph_dispatch + exporter formatters
  ([`e655ec0`](https://github.com/n24q02m/better-code-review-graph/commit/e655ec0590043fff47908cd61d5cce004059516a))

- Document graph.export + graph.summarize in help topic + README v1.6 callout
  ([`a656567`](https://github.com/n24q02m/better-code-review-graph/commit/a65656735b98506630585f18c15d62770e9244dd))

- Graph(action='export') with graphml + json-ld + dot + cypher formats
  ([`aaa1f08`](https://github.com/n24q02m/better-code-review-graph/commit/aaa1f0880ef9e73bc1c5d9b406dbd93302710f28))

- Harden summarize_node against empty SDK responses + brace-safe prompt
  ([`e63cb6c`](https://github.com/n24q02m/better-code-review-graph/commit/e63cb6c7a9331450dc471590216cff6de882f46c))

- Link to mcp.n24q02m.com unified docs site (Spec F Phase 4)
  ([`d13d104`](https://github.com/n24q02m/better-code-review-graph/commit/d13d1047c77b5a6f7997c6c37d09a3551fdf53a9))

- Lock empty-string + unicode + frozen contracts in summarizer tests
  ([`8dcac22`](https://github.com/n24q02m/better-code-review-graph/commit/8dcac22034c7d228e146fa201470566aa3d7c870))

- Lock per-node persistence + empty-string cache-miss contracts in batch tests
  ([`310d287`](https://github.com/n24q02m/better-code-review-graph/commit/310d2873e8b3c3fdf0aeeedb083f259a165e7b4f))

- Parser populates Function source_text + upsert_node persists it
  ([`79cb3bf`](https://github.com/n24q02m/better-code-review-graph/commit/79cb3bf553cc6fbad0c6337597f235b36df0544b))

- Summarize_node single-node LLM summary via Gemini or OpenAI
  ([`a90f17c`](https://github.com/n24q02m/better-code-review-graph/commit/a90f17ceaa957f41991390a86d0facd91a50fc71))

- Summarizer cache key derivation + provider env-var detection
  ([`22b446e`](https://github.com/n24q02m/better-code-review-graph/commit/22b446e7c8227b5c95384dd058d571b2ec82022e))

- Sync cross-promo section ([#449](https://github.com/n24q02m/better-code-review-graph/pull/449),
  [`8534ffe`](https://github.com/n24q02m/better-code-review-graph/commit/8534ffeee80019a567478cb6a54c117c52f29895))

- Wire graph(action='summarize') MCP action with cost cap + provider auto-detect
  ([`a1c2182`](https://github.com/n24q02m/better-code-review-graph/commit/a1c218263439c0c926abc0523d67643d440cf141))

### Testing

- Add error path coverage for graph build/update
  ([`89dd791`](https://github.com/n24q02m/better-code-review-graph/commit/89dd791a219bf67d15570d79474e6cd1439fe287))

- Add robust error path coverage for graph build/update
  ([`89dd791`](https://github.com/n24q02m/better-code-review-graph/commit/89dd791a219bf67d15570d79474e6cd1439fe287))


## v3.14.0 (2026-05-06)

### Bug Fixes

- Regenerate uv.lock with UV_NO_SOURCES for Docker build
  ([`986bbde`](https://github.com/n24q02m/better-code-review-graph/commit/986bbde219ede531ca9041e1932afc34b5f21d03))


## v3.14.0-beta.1 (2026-05-06)

### Bug Fixes

- Consolidate setup docs body to 3 methods (drop legacy Method 4/5)
  ([#421](https://github.com/n24q02m/better-code-review-graph/pull/421),
  [`8337cd5`](https://github.com/n24q02m/better-code-review-graph/commit/8337cd5a1c6d673dd6a258e7014839ce45840d39))

- Restore test coverage above 95% threshold for v1.7 features
  ([`572f474`](https://github.com/n24q02m/better-code-review-graph/commit/572f474543235a80c66887afd986ec7ea91c89ad))

- **deps**: Update non-major dependencies
  ([#428](https://github.com/n24q02m/better-code-review-graph/pull/428),
  [`5588988`](https://github.com/n24q02m/better-code-review-graph/commit/5588988c2ddfe004e8b5b06cf7b52804058903c8))

### Chores

- **deps**: Update step-security/harden-runner digest to a5ad31d
  ([#412](https://github.com/n24q02m/better-code-review-graph/pull/412),
  [`2bd88d1`](https://github.com/n24q02m/better-code-review-graph/commit/2bd88d18d36104b5a035cfa42162dbcccbdc6748))

### Features

- Add embeddings_count + keyword_only to query/search response header
  ([`14355be`](https://github.com/n24q02m/better-code-review-graph/commit/14355be4d6dfa23c9de2ca74ced2005ea8476cc0))

- Add explicit Method overview section to setup docs
  ([#420](https://github.com/n24q02m/better-code-review-graph/pull/420),
  [`691ee39`](https://github.com/n24q02m/better-code-review-graph/commit/691ee39da8847c3328cd49e77b2b335d8f6399a8))

- Add query.renamed_in_diff for symbol callsite line drift vs base ref
  ([`3e1511c`](https://github.com/n24q02m/better-code-review-graph/commit/3e1511c50cf29d60c23bccf0f6879e04de3c08d6))

- Add query.spot_check action for random callsite source samples
  ([`54bdc5a`](https://github.com/n24q02m/better-code-review-graph/commit/54bdc5ae00b2def861e6565dba4d96021e0aff98))

- Add recipes topic to help with stage-mapped operational patterns
  ([`1b6a9cf`](https://github.com/n24q02m/better-code-review-graph/commit/1b6a9cf09b13fbf5d1374771ddf51f5cd0c1595c))

- Add reviewer_summary to graph update response
  ([`8e4d1e7`](https://github.com/n24q02m/better-code-review-graph/commit/8e4d1e72402c342a2c623d82af9c1c2629d8deef))

- Align userConfig with relay_schema fields
  ([#425](https://github.com/n24q02m/better-code-review-graph/pull/425),
  [`916d7e9`](https://github.com/n24q02m/better-code-review-graph/commit/916d7e95a095685b8bea6ee0a156047e6659757b))

- Auto-pick Function over File for callers_of/callees_of bare-name
  ([`dc22290`](https://github.com/n24q02m/better-code-review-graph/commit/dc222908fa277c37fbf33502edb1d9fa24712c5b))

- Auto-truncate impact response when payload exceeds size cap
  ([`030faef`](https://github.com/n24q02m/better-code-review-graph/commit/030faef605631c238f27006a9b1e9c5366b2632f))

- Declare userConfig schema and document install prompt
  ([#422](https://github.com/n24q02m/better-code-review-graph/pull/422),
  [`ca6f34d`](https://github.com/n24q02m/better-code-review-graph/commit/ca6f34d08e31477609a719558ebefc8606f4328d))

- Document userConfig credential prompts per plugin
  ([#426](https://github.com/n24q02m/better-code-review-graph/pull/426),
  [`83c9d04`](https://github.com/n24q02m/better-code-review-graph/commit/83c9d0418df2033a7474015b482f195cc9dc3e50))

- Note CC scope-by-endpoint mutual exclusivity rule
  ([#427](https://github.com/n24q02m/better-code-review-graph/pull/427),
  [`a8a8596`](https://github.com/n24q02m/better-code-review-graph/commit/a8a8596ebd9931fde3d61f1c60561089989021c8))

- Surface dynamic-dispatch hints in callers_of/callees_of response
  ([`6e60644`](https://github.com/n24q02m/better-code-review-graph/commit/6e606448137f8206429e0586b2a13851724bf7db))

- Warn at search when keyword fallback meets phrase-shape query
  ([`427770f`](https://github.com/n24q02m/better-code-review-graph/commit/427770f0591d91319acecc7b51153c6d6649a639))


## v3.13.0 (2026-05-04)

### Bug Fixes

- Bump mcp-core to 1.13.0 (STABLE)
  ([#419](https://github.com/n24q02m/better-code-review-graph/pull/419),
  [`34f2770`](https://github.com/n24q02m/better-code-review-graph/commit/34f2770f371f42072d29dbfc8912f3d8dad9087c))


## v3.13.0-beta.10 (2026-05-03)

### Features

- Bump mcp-core to 1.13.0-beta.7
  ([#414](https://github.com/n24q02m/better-code-review-graph/pull/414),
  [`7d5f70d`](https://github.com/n24q02m/better-code-review-graph/commit/7d5f70d10ae3e7214e3ae3eecaabbb2f82f9f97c))

- Document MCP_RELAY_PASSWORD edge auth gate
  ([#415](https://github.com/n24q02m/better-code-review-graph/pull/415),
  [`6457004`](https://github.com/n24q02m/better-code-review-graph/commit/6457004c225bcf3c47556e323809394e5a11951d))


## v3.13.0-beta.9 (2026-05-03)

### Bug Fixes

- HTTP multi-user credential wiring (per-sub contextvar)
  ([#413](https://github.com/n24q02m/better-code-review-graph/pull/413),
  [`4e77192`](https://github.com/n24q02m/better-code-review-graph/commit/4e771929f5216dd0da9e9b8e0be1d3f1f1859390))


## v3.13.0-beta.8 (2026-05-02)

### Bug Fixes

- Regenerate uv.lock for new mcp-core beta (Docker trap)
  ([#411](https://github.com/n24q02m/better-code-review-graph/pull/411),
  [`04453e1`](https://github.com/n24q02m/better-code-review-graph/commit/04453e1ee9ea72f88917a0929fcc180dc64768e1))


## v3.13.0-beta.7 (2026-05-02)

### Bug Fixes

- Gate PerPluginStore fallback behind HTTP mode (stdio-pure spec §4.1)
  ([#410](https://github.com/n24q02m/better-code-review-graph/pull/410),
  [`7abeb4c`](https://github.com/n24q02m/better-code-review-graph/commit/7abeb4c96685f641a1f75f62c9a6b18b054aa22e))


## v3.13.0-beta.6 (2026-05-02)

### Bug Fixes

- Regenerate uv.lock UV_NO_SOURCES=1 (Docker build trap)
  ([#409](https://github.com/n24q02m/better-code-review-graph/pull/409),
  [`7119a0e`](https://github.com/n24q02m/better-code-review-graph/commit/7119a0e4cbfb85ac04854747f587625e9f5e4461))


## v3.13.0-beta.5 (2026-05-02)

### Bug Fixes

- Setup docs + README reflect stdio-pure architecture
  ([#408](https://github.com/n24q02m/better-code-review-graph/pull/408),
  [`39e4090`](https://github.com/n24q02m/better-code-review-graph/commit/39e40907a5b074b72f747e0b9dc1d191475f2a20))

- **deps**: Update non-major dependencies
  ([#403](https://github.com/n24q02m/better-code-review-graph/pull/403),
  [`bb8eedd`](https://github.com/n24q02m/better-code-review-graph/commit/bb8eedd25a94fa4dc79b8a74c8fa1dd6a36153ad))

### Chores

- **deps**: Update github/codeql-action digest to 0daab03
  ([#405](https://github.com/n24q02m/better-code-review-graph/pull/405),
  [`2ddaf8a`](https://github.com/n24q02m/better-code-review-graph/commit/2ddaf8a99e0bcc6fd699add76101a3483b2a0454))

### Features

- Stdio-pure + http-multi-user (drop daemon-bridge)
  ([#407](https://github.com/n24q02m/better-code-review-graph/pull/407),
  [`2cc52fd`](https://github.com/n24q02m/better-code-review-graph/commit/2cc52fd4917313c4f2cc10b333742e9fa306ea3c))


## v3.13.0-beta.4 (2026-04-30)

### Bug Fixes

- G6 UX status accuracy — derive state from live PerPluginStore
  ([#404](https://github.com/n24q02m/better-code-review-graph/pull/404),
  [`8d83382`](https://github.com/n24q02m/better-code-review-graph/commit/8d833828dc4e118875a3d3757c7bbe7bcf27cc18))

- Re-trigger CI after mcp-core lint+format fix
  ([#402](https://github.com/n24q02m/better-code-review-graph/pull/402),
  [`68908d9`](https://github.com/n24q02m/better-code-review-graph/commit/68908d957e6ebde80ca6cdb3c6bbce5be62a289c))

- Ruff sort imports in test_per_plugin_storage_migration.py
  ([#402](https://github.com/n24q02m/better-code-review-graph/pull/402),
  [`68908d9`](https://github.com/n24q02m/better-code-review-graph/commit/68908d957e6ebde80ca6cdb3c6bbce5be62a289c))

### Features

- **docs**: Add trust model section to README
  ([#401](https://github.com/n24q02m/better-code-review-graph/pull/401),
  [`d46bb32`](https://github.com/n24q02m/better-code-review-graph/commit/d46bb324f4dcae5bed5ed0d07036718b6d81a767))

- **storage**: Migrate to PerPluginStore from mcp-core 1.13.0b1+
  ([#402](https://github.com/n24q02m/better-code-review-graph/pull/402),
  [`68908d9`](https://github.com/n24q02m/better-code-review-graph/commit/68908d957e6ebde80ca6cdb3c6bbce5be62a289c))


## v3.13.0-beta.3 (2026-04-30)

### Bug Fixes

- Regenerate uv.lock with UV_NO_SOURCES=1 to remove local path references
  ([#399](https://github.com/n24q02m/better-code-review-graph/pull/399),
  [`f7381d3`](https://github.com/n24q02m/better-code-review-graph/commit/f7381d3c4940ed548c83a52fe2eae88f1fab14d1))


## v3.13.0-beta.2 (2026-04-30)

### Bug Fixes

- Strip [tool.uv.sources] in Dockerfile to fix uv sync --frozen Docker build
  ([#398](https://github.com/n24q02m/better-code-review-graph/pull/398),
  [`500b8bb`](https://github.com/n24q02m/better-code-review-graph/commit/500b8bb261be73c19b521226ce96b11d7382d548))


## v3.13.0-beta.1 (2026-04-30)

### Features

- Route stdio mode to FastMCP direct + multi-target Dockerfile
  ([#397](https://github.com/n24q02m/better-code-review-graph/pull/397),
  [`ba0f159`](https://github.com/n24q02m/better-code-review-graph/commit/ba0f1597b3bd5fb7c5c33d3e4dc8cf708bb3d23d))


## v3.12.5 (2026-04-29)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.11.3 for D17 tools cache refresh
  ([#394](https://github.com/n24q02m/better-code-review-graph/pull/394),
  [`3618982`](https://github.com/n24q02m/better-code-review-graph/commit/361898248a6bdfda8ad6d1c07b2135740994e2fc))


## v3.12.4 (2026-04-29)

### Bug Fixes

- Rebuild uv.lock without local path source
  ([#391](https://github.com/n24q02m/better-code-review-graph/pull/391),
  [`a6bac96`](https://github.com/n24q02m/better-code-review-graph/commit/a6bac963ef05c55311771429fce345f913e5413e))


## v3.12.3 (2026-04-29)

### Bug Fixes

- Not_found reason discriminator + languages filter (D15+D16, fixes #339 #340)
  ([#387](https://github.com/n24q02m/better-code-review-graph/pull/387),
  [`ec6654a`](https://github.com/n24q02m/better-code-review-graph/commit/ec6654ae466b5b8bd56ea9b1c85193b8bbdd873a))

- Register config__open_relay tool (Transparent Bridge Wave 3)
  ([#389](https://github.com/n24q02m/better-code-review-graph/pull/389),
  [`f03e9ed`](https://github.com/n24q02m/better-code-review-graph/commit/f03e9ed090865c2e296cb12c9de7a7a299f5bb8b))

- **deps**: Update dawidd6/action-send-mail action to v17
  ([#386](https://github.com/n24q02m/better-code-review-graph/pull/386),
  [`e51b99c`](https://github.com/n24q02m/better-code-review-graph/commit/e51b99c843acba6421c910d303da8b17cb3971ae))

- **deps**: Update non-major dependencies
  ([#385](https://github.com/n24q02m/better-code-review-graph/pull/385),
  [`225b3b3`](https://github.com/n24q02m/better-code-review-graph/commit/225b3b3f540a4559dc85300aeb16f3784d5a5c12))


## v3.12.2 (2026-04-28)

### Bug Fixes

- Pass MCP_TRANSPORT=stdio in plugin.json + uv run --no-sync hooks
  ([#380](https://github.com/n24q02m/better-code-review-graph/pull/380),
  [`8706fa1`](https://github.com/n24q02m/better-code-review-graph/commit/8706fa14ce5a9aa992eebef6f8c7d6cf095cb0ff))

- Pass MCP_TRANSPORT=stdio in plugin.json + uv run --no-sync hooks
  ([#379](https://github.com/n24q02m/better-code-review-graph/pull/379),
  [`369e28a`](https://github.com/n24q02m/better-code-review-graph/commit/369e28ade1eb162490f5cb212a52433cf52bf1b6))

- **credentials**: Rip _share_cloud_keys_to_peers — per-server isolation
  ([#380](https://github.com/n24q02m/better-code-review-graph/pull/380),
  [`8706fa1`](https://github.com/n24q02m/better-code-review-graph/commit/8706fa14ce5a9aa992eebef6f8c7d6cf095cb0ff))

- **deps**: Bump n24q02m-mcp-core to 1.10.0 — Transparent Bridge waves 1-3
  ([#382](https://github.com/n24q02m/better-code-review-graph/pull/382),
  [`6469340`](https://github.com/n24q02m/better-code-review-graph/commit/646934026f26efae500c80cb75e86f3eada3ba44))

- **lint**: Ruff format pass ([#380](https://github.com/n24q02m/better-code-review-graph/pull/380),
  [`8706fa1`](https://github.com/n24q02m/better-code-review-graph/commit/8706fa14ce5a9aa992eebef6f8c7d6cf095cb0ff))

- **test**: Cover multi-user save_credentials + per-sub helpers (95% coverage)
  ([#380](https://github.com/n24q02m/better-code-review-graph/pull/380),
  [`8706fa1`](https://github.com/n24q02m/better-code-review-graph/commit/8706fa14ce5a9aa992eebef6f8c7d6cf095cb0ff))


## v3.12.1 (2026-04-28)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.9.0
  ([#378](https://github.com/n24q02m/better-code-review-graph/pull/378),
  [`23a8526`](https://github.com/n24q02m/better-code-review-graph/commit/23a85263df6826176142453ddb1a25340a521e7e))

- **deps**: Update dependency qwen3-embed to >=1.9.1
  ([#374](https://github.com/n24q02m/better-code-review-graph/pull/374),
  [`edddd98`](https://github.com/n24q02m/better-code-review-graph/commit/edddd987fed0b12a6d9af700fae81f3c8d0873c1))


## v3.12.0 (2026-04-27)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.8.1
  ([#371](https://github.com/n24q02m/better-code-review-graph/pull/371),
  [`39796de`](https://github.com/n24q02m/better-code-review-graph/commit/39796de0ea6b6840cd4d4dd579c69272d75128fc))

### Chores

- **deps**: Update dependency ruff to >=0.15.12
  ([#364](https://github.com/n24q02m/better-code-review-graph/pull/364),
  [`a521040`](https://github.com/n24q02m/better-code-review-graph/commit/a5210404e8dab8039d9a74f755594f32f49d0420))

### Features

- Add ## E2E section to CLAUDE.md per Task 21 docs rollout
  ([#368](https://github.com/n24q02m/better-code-review-graph/pull/368),
  [`a930474`](https://github.com/n24q02m/better-code-review-graph/commit/a9304743cf913277686782e3ce137ba3618bfce4))

### Performance Improvements

- **embeddings**: Optimize embedding insertions using executemany
  ([#366](https://github.com/n24q02m/better-code-review-graph/pull/366),
  [`0fcde8d`](https://github.com/n24q02m/better-code-review-graph/commit/0fcde8d1d525beb78454942eab0761e2e566059c))


## v3.12.0-beta.3 (2026-04-27)

### Bug Fixes

- Chown /app to appuser so runtime state dirs are writable
  ([`530dfb4`](https://github.com/n24q02m/better-code-review-graph/commit/530dfb4ae438c09e03d36a869d78d3c9f61110a7))


## v3.12.0-beta.2 (2026-04-27)

### Bug Fixes

- Copy src/ before uv sync so the project actually installs
  ([`19c21b2`](https://github.com/n24q02m/better-code-review-graph/commit/19c21b214bb13f6e7654f02f0fe37e7bbaba5dd9))


## v3.12.0-beta.1 (2026-04-27)

### Bug Fixes

- Sweep doppler/infisical refs to skret SSM
  ([`6c315c6`](https://github.com/n24q02m/better-code-review-graph/commit/6c315c6b8f3552b71f66e8972f338475e33b24b9))

### Features

- Crg per-JWT-sub graph DB + storage for multi-user remote
  ([#367](https://github.com/n24q02m/better-code-review-graph/pull/367),
  [`11c99bd`](https://github.com/n24q02m/better-code-review-graph/commit/11c99bd10e58aa1e2f38e9b862b380a2b91c4b1a))


## v3.11.1 (2026-04-24)

### Bug Fixes

- Regenerate uv.lock without [tool.uv.sources] for Docker build
  ([#363](https://github.com/n24q02m/better-code-review-graph/pull/363),
  [`70825bd`](https://github.com/n24q02m/better-code-review-graph/commit/70825bd21a6b3c5e2c3a6385faa1cc56f519931e))


## v3.11.0 (2026-04-24)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.7.6
  ([#362](https://github.com/n24q02m/better-code-review-graph/pull/362),
  [`88d0e3a`](https://github.com/n24q02m/better-code-review-graph/commit/88d0e3a10fa88c57f46e1acd49191d46e3c73eec))

- Bump n24q02m-mcp-core to >=1.7.1
  ([#356](https://github.com/n24q02m/better-code-review-graph/pull/356),
  [`e604a1d`](https://github.com/n24q02m/better-code-review-graph/commit/e604a1de78a52d9fa3f2d2c50c2fc972e47f9934))

### Chores

- **deps**: Update python:3.13-slim-bookworm docker digest to bb73517
  ([#352](https://github.com/n24q02m/better-code-review-graph/pull/352),
  [`65bed63`](https://github.com/n24q02m/better-code-review-graph/commit/65bed638b88d9540cdfadee7c9685a2f59ffa5a8))

### Features

- Enforce Smart Daemon Manager (1-Daemon) for stdio transport
  ([`924178c`](https://github.com/n24q02m/better-code-review-graph/commit/924178c0d0fe14d9a1610a9a196cd898eafa5fc6))


## v3.10.5 (2026-04-22)

### Bug Fixes

- Bump mcp-core to 1.6.2 ([#351](https://github.com/n24q02m/better-code-review-graph/pull/351),
  [`fb209b0`](https://github.com/n24q02m/better-code-review-graph/commit/fb209b09414125a81356e4717edb26d1f7ec9e37))

- Bump mcp-core to 1.6.3 ([#351](https://github.com/n24q02m/better-code-review-graph/pull/351),
  [`fb209b0`](https://github.com/n24q02m/better-code-review-graph/commit/fb209b09414125a81356e4717edb26d1f7ec9e37))

- Bump n24q02m-mcp-core to 1.6.3 (relay form follow redirect_url)
  ([#351](https://github.com/n24q02m/better-code-review-graph/pull/351),
  [`fb209b0`](https://github.com/n24q02m/better-code-review-graph/commit/fb209b09414125a81356e4717edb26d1f7ec9e37))


## v3.10.4 (2026-04-22)

### Bug Fixes

- Bump mcp-core to 1.6.2 ([#349](https://github.com/n24q02m/better-code-review-graph/pull/349),
  [`2afbef1`](https://github.com/n24q02m/better-code-review-graph/commit/2afbef1c3587c89f070e347612577695898f6f09))


## v3.10.3 (2026-04-22)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.5.1
  ([`7a38355`](https://github.com/n24q02m/better-code-review-graph/commit/7a38355df4819e0ed73091ff18ee384fe360ff1e))

- Bump n24q02m-mcp-core to 1.6.1
  ([#345](https://github.com/n24q02m/better-code-review-graph/pull/345),
  [`5c35142`](https://github.com/n24q02m/better-code-review-graph/commit/5c35142ea0bfd4673fb86a779122f8b1a5303d04))

- Ignore local dev utility clean.ps1
  ([#345](https://github.com/n24q02m/better-code-review-graph/pull/345),
  [`5c35142`](https://github.com/n24q02m/better-code-review-graph/commit/5c35142ea0bfd4673fb86a779122f8b1a5303d04))

- Require explicit MCP_RELAY_URL for remote-relay mode
  ([#345](https://github.com/n24q02m/better-code-review-graph/pull/345),
  [`5c35142`](https://github.com/n24q02m/better-code-review-graph/commit/5c35142ea0bfd4673fb86a779122f8b1a5303d04))

- Require explicit MCP_RELAY_URL for remote-relay mode per matrix 2.5
  ([#345](https://github.com/n24q02m/better-code-review-graph/pull/345),
  [`5c35142`](https://github.com/n24q02m/better-code-review-graph/commit/5c35142ea0bfd4673fb86a779122f8b1a5303d04))

- **deps**: Update dependency qwen3-embed to >=1.9.0
  ([#342](https://github.com/n24q02m/better-code-review-graph/pull/342),
  [`cd95597`](https://github.com/n24q02m/better-code-review-graph/commit/cd9559736d44104dd607b2c9d35762d784078396))

### Chores

- **deps**: Lock file maintenance
  ([#344](https://github.com/n24q02m/better-code-review-graph/pull/344),
  [`2d12a94`](https://github.com/n24q02m/better-code-review-graph/commit/2d12a949dad97bf3ec78c1c94a5c773bd61c68b2))

- **deps**: Update astral-sh/setup-uv action to v8
  ([#343](https://github.com/n24q02m/better-code-review-graph/pull/343),
  [`a26ea8a`](https://github.com/n24q02m/better-code-review-graph/commit/a26ea8a99d4a7c9187d804725ecc52d30e833508))


## v3.10.2 (2026-04-21)

### Bug Fixes

- Bump non-major Python deps incl mcp-core to 1.5.0
  ([`9f7410f`](https://github.com/n24q02m/better-code-review-graph/commit/9f7410f47337e423076e0874379512a92cc3f5bf))

- Bump step-security/harden-runner digest to 8d3c67d
  ([`16f103f`](https://github.com/n24q02m/better-code-review-graph/commit/16f103f2c0e9a909147776d544de49f82259094a))

- Lock file maintenance
  ([`3f76346`](https://github.com/n24q02m/better-code-review-graph/commit/3f7634674b9913253e51a44d5a22e8cab115de01))

- Push target filter to SQL json_each in get_edges_among
  ([`b6be9cc`](https://github.com/n24q02m/better-code-review-graph/commit/b6be9cc751092e318098c5b807c07e2fb7d4e90b))

- Widen incremental update base to cover all local commits
  ([`aebbe43`](https://github.com/n24q02m/better-code-review-graph/commit/aebbe43b91769e422042673de90f34099ffdface))


## v3.10.1 (2026-04-21)

### Bug Fixes

- Accept SubjectContext arg on save_credentials
  ([`6a02e3a`](https://github.com/n24q02m/better-code-review-graph/commit/6a02e3af7fe8279604142cd819707be154d05f5c))

- Remove unnecessary chunking for json_each SQLite queries
  ([`bc44122`](https://github.com/n24q02m/better-code-review-graph/commit/bc44122cae23b533d3ac938cbf6a23ad9a6d800b))

- Stdio fallback spawns local credential form, not remote relay
  ([`744da0f`](https://github.com/n24q02m/better-code-review-graph/commit/744da0fe95f82113b2984f5b0094b2721050e11a))

- **deps**: Bump mcp-core to 1.4.3
  ([`4dfebf7`](https://github.com/n24q02m/better-code-review-graph/commit/4dfebf70c402439360f5db3e1e383d56beae0f3f))

- **deps**: Lock file maintenance (filelock 3.28.0->3.29.0)
  ([`961d945`](https://github.com/n24q02m/better-code-review-graph/commit/961d945adbc909c77d604a06e49eef3116b7d3e7))


## v3.10.0 (2026-04-19)

### Bug Fixes

- Add error handling to build_or_update_graph and add coverage tests
  ([#287](https://github.com/n24q02m/better-code-review-graph/pull/287),
  [`ef98bdf`](https://github.com/n24q02m/better-code-review-graph/commit/ef98bdf5e384c7475d45cadafb33ed19c3e134e9))

- Auto-select cloud embedding model based on available API key
  ([`9babf4f`](https://github.com/n24q02m/better-code-review-graph/commit/9babf4f6d2e0cc8b008631317c51fdd702338ba2))

- Bump mcp-core to 1.3.0 ([#308](https://github.com/n24q02m/better-code-review-graph/pull/308),
  [`2d6f58e`](https://github.com/n24q02m/better-code-review-graph/commit/2d6f58e1ea945dd4d9c26743480a6ddb664f8034))

- Bump n24q02m-mcp-core to 1.4.0
  ([#312](https://github.com/n24q02m/better-code-review-graph/pull/312),
  [`8e28b0a`](https://github.com/n24q02m/better-code-review-graph/commit/8e28b0a4d3fa0c82848eaabf8fefc995cb2af57e))

- N+1 queries in embed_nodes ([#305](https://github.com/n24q02m/better-code-review-graph/pull/305),
  [`52e186a`](https://github.com/n24q02m/better-code-review-graph/commit/52e186a41adab0d20802fe12934f94df89904f33))

- Refactor overly long get_review_context function
  ([#295](https://github.com/n24q02m/better-code-review-graph/pull/295),
  [`7595731`](https://github.com/n24q02m/better-code-review-graph/commit/7595731b615c776b72f47355f63fd429b8551c43))

- Refactor overly long watch function and extract helper
  ([#291](https://github.com/n24q02m/better-code-review-graph/pull/291),
  [`5b9950b`](https://github.com/n24q02m/better-code-review-graph/commit/5b9950b3fa553695f1d110f5220edd03eb1a80d9))

- Split overly long query_graph function into smaller helpers
  ([#288](https://github.com/n24q02m/better-code-review-graph/pull/288),
  [`931c638`](https://github.com/n24q02m/better-code-review-graph/commit/931c638725ea66732ee9c341f3ee0d956c7c5122))

- Untrack .jules AI traces + gitignore AI-trace dirs
  ([`bdbd69d`](https://github.com/n24q02m/better-code-review-graph/commit/bdbd69d3fa026114a154d413aed0b0ca7d954f42))

- **security**: Eliminate structural dynamic SQL in GraphStore
  ([#297](https://github.com/n24q02m/better-code-review-graph/pull/297),
  [`db24cba`](https://github.com/n24q02m/better-code-review-graph/commit/db24cbadff0177aef0435e4f7fb6d4dd950a466f))

### Chores

- **deps**: Lock file maintenance
  ([#309](https://github.com/n24q02m/better-code-review-graph/pull/309),
  [`c2fbbae`](https://github.com/n24q02m/better-code-review-graph/commit/c2fbbaead6ba533dd519b7ea724adca88557936a))

- **deps**: Lock file maintenance
  ([#304](https://github.com/n24q02m/better-code-review-graph/pull/304),
  [`a82e1ea`](https://github.com/n24q02m/better-code-review-graph/commit/a82e1eac71f22ae9f906e3a0fd48a584961b999c))

- **deps**: Update github/codeql-action digest to ce64ddc
  ([#303](https://github.com/n24q02m/better-code-review-graph/pull/303),
  [`525779a`](https://github.com/n24q02m/better-code-review-graph/commit/525779a49cf7c7dad070b912fefdc8b8a2b2ddf4))

### Features

- Merge setup tool into config with setup_* sub-actions
  ([#307](https://github.com/n24q02m/better-code-review-graph/pull/307),
  [`c6dbd9e`](https://github.com/n24q02m/better-code-review-graph/commit/c6dbd9e15e9f15db4804885cacaa99e27ce8a6c1))

### Performance Improvements

- Optimize get_subgraph by removing redundant mapping
  ([#294](https://github.com/n24q02m/better-code-review-graph/pull/294),
  [`e63fce2`](https://github.com/n24q02m/better-code-review-graph/commit/e63fce2a1cf1291fbd54796f3cffc9742ad9866a))

### Refactoring

- Split _extract_from_tree into specialized handlers
  ([#292](https://github.com/n24q02m/better-code-review-graph/pull/292),
  [`931237e`](https://github.com/n24q02m/better-code-review-graph/commit/931237ed980396dd1211fb7e1c4c017d1f1adf32))

### Testing

- Add comprehensive tests for callers_of query pattern
  ([#289](https://github.com/n24q02m/better-code-review-graph/pull/289),
  [`bc09fa2`](https://github.com/n24q02m/better-code-review-graph/commit/bc09fa21b401f4222a655bcaf3ef44054e269f87))

- Add error test for query_graph invalid pattern
  ([#280](https://github.com/n24q02m/better-code-review-graph/pull/280),
  [`c241243`](https://github.com/n24q02m/better-code-review-graph/commit/c241243c0fd8980d15b9e8da8e35db0478585e0f))


## v3.9.2 (2026-04-17)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.2.0 (authlib CVE patch)
  ([`6fd113b`](https://github.com/n24q02m/better-code-review-graph/commit/6fd113b56c3327b74257d370ac6f58626e5e216b))


## v3.9.1 (2026-04-17)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.1.1 for OAuth issuer fix
  ([`d1f45bc`](https://github.com/n24q02m/better-code-review-graph/commit/d1f45bcea8d888e190dd58cf3d8f69a01207e708))


## v3.9.0 (2026-04-17)

### Bug Fixes

- Add diacritic preservation pre-commit hook
  ([#300](https://github.com/n24q02m/better-code-review-graph/pull/300),
  [`2e959c9`](https://github.com/n24q02m/better-code-review-graph/commit/2e959c9c701fbb8407a9888f7d4e48fd948f8580))

- Add tests for config() set action error paths
  ([#244](https://github.com/n24q02m/better-code-review-graph/pull/244),
  [`f5a35cd`](https://github.com/n24q02m/better-code-review-graph/commit/f5a35cdd5c22c30aa47110c6c3f7be5602bfee29))

- Add tests for help() function missing match
  ([#241](https://github.com/n24q02m/better-code-review-graph/pull/241),
  [`220cb1c`](https://github.com/n24q02m/better-code-review-graph/commit/220cb1c0bb97c3d578f0679d53c8eaf1efecb3d6))

- Add tests for relay_setup ensure_config error handling
  ([#240](https://github.com/n24q02m/better-code-review-graph/pull/240),
  [`9ddb968`](https://github.com/n24q02m/better-code-review-graph/commit/9ddb968d6fd90ba9bb8945af4b8d4139d07190a2))

- Add tests for search_roots fallback in get_docs_section
  ([#246](https://github.com/n24q02m/better-code-review-graph/pull/246),
  [`427a583`](https://github.com/n24q02m/better-code-review-graph/commit/427a58381c5a533313fa0371a5db47cdcedcdd98))

- Bandit B608 SQL injection risk
  ([`1ff8386`](https://github.com/n24q02m/better-code-review-graph/commit/1ff83868d95fcdb51691a3fe8f7fa766a5a6e535))

- Batch file queries with get_nodes_by_files to eliminate N+1 in impact radius and embed_all_nodes
  ([#298](https://github.com/n24q02m/better-code-review-graph/pull/298),
  [`b4f2bfb`](https://github.com/n24q02m/better-code-review-graph/commit/b4f2bfbbe0cc38f143bd196ed046f871112cb71a))

- Bump authlib + pytest for CSRF cache bypass and tmpdir CVE
  ([`e924c20`](https://github.com/n24q02m/better-code-review-graph/commit/e924c203a8e70726927be527e1d77464e71837ea))

- Bump n24q02m-mcp-core to >=1.0.0 stable
  ([`a7c83e3`](https://github.com/n24q02m/better-code-review-graph/commit/a7c83e3528d857cd51dc0a2a9b03000f41d194d5))

- Bump pytest to v9 for security advisory
  ([#276](https://github.com/n24q02m/better-code-review-graph/pull/276),
  [`2b764e4`](https://github.com/n24q02m/better-code-review-graph/commit/2b764e4cbaa4d985204e6ef6496079dee14fbc16))

- Correct import paths in test_performance_n1 to fix coverage measurement
  ([`92d0541`](https://github.com/n24q02m/better-code-review-graph/commit/92d0541e3eb247ee2a6f3c01f8f6a0d36e1a5363))

- Drop local uv.sources override for n24q02m-mcp-core
  ([`5726f06`](https://github.com/n24q02m/better-code-review-graph/commit/5726f0678fee1b61b911eb871f105935202d833a))

- Lock file maintenance
  ([`c47180b`](https://github.com/n24q02m/better-code-review-graph/commit/c47180b6a4850b4c94da9705e6c74c6b6213738b))

- Loosen N+1 perf threshold to tolerate CI jitter
  ([`8d84c97`](https://github.com/n24q02m/better-code-review-graph/commit/8d84c976fdbd0d868f590fa3cd84c91bb25ee0a7))

- Raise crg coverage to 95% by covering apply_config + save_credentials
  ([`1e501f4`](https://github.com/n24q02m/better-code-review-graph/commit/1e501f41f9e2904f8c9c0847b57f6c8f08de3117))

- Sync docs with Phase M completion reality
  ([#299](https://github.com/n24q02m/better-code-review-graph/pull/299),
  [`795310a`](https://github.com/n24q02m/better-code-review-graph/commit/795310a270681561ce43a7a429c361616d6be3cf))

- Tighten credential_state + test helper typing in crg
  ([`a061461`](https://github.com/n24q02m/better-code-review-graph/commit/a061461919d9c6bf02c73b0e7a34dd1a7d56f864))

- Tighten embeddings, parser, and relay typing in crg
  ([`e2baa2f`](https://github.com/n24q02m/better-code-review-graph/commit/e2baa2f3f8b44cf5e2c2b3fb1377d2dd881ecc37))

- Update docker/build-push-action digest to bcafcac
  ([`c9fe401`](https://github.com/n24q02m/better-code-review-graph/commit/c9fe4010838dc101c2b347d395e66837bce6da16))

- Update fastmcp to 3.2.0 and Pygments to 2.20.0 to fix SSRF, command injection, OAuth, and ReDoS
  vulnerabilities
  ([`0520358`](https://github.com/n24q02m/better-code-review-graph/commit/05203587afa94f952e15956af165df33c2853add))

- Update non-major dependencies
  ([`1e3d093`](https://github.com/n24q02m/better-code-review-graph/commit/1e3d093642631bdbad7a27263e798ceea3460d3a))

- Update python:3.13-slim-bookworm docker digest to 061b6e5
  ([`3dbd6bc`](https://github.com/n24q02m/better-code-review-graph/commit/3dbd6bcd61bbbba6a5f1f5a0a0d6d42a8fe6589f))

- **deps**: Bump actions/create-github-app-token digest to 1b10c78
  ([#269](https://github.com/n24q02m/better-code-review-graph/pull/269),
  [`c501ff2`](https://github.com/n24q02m/better-code-review-graph/commit/c501ff2000e72874560901bcae35fff91a1200f1))

- **deps**: Bump actions/upload-artifact digest to 043fb46
  ([#270](https://github.com/n24q02m/better-code-review-graph/pull/270),
  [`e480cc4`](https://github.com/n24q02m/better-code-review-graph/commit/e480cc46fd06c50db81d6640b2ea58a681f84410))

- **deps**: Bump non-major dependencies (cohere, fastmcp, google-genai, openai, mcp-core 1.1.0)
  ([#272](https://github.com/n24q02m/better-code-review-graph/pull/272),
  [`7962889`](https://github.com/n24q02m/better-code-review-graph/commit/7962889856da170de07e9f3d4a48d70573de4bd9))

- **deps**: Bump step-security/harden-runner digest to 6c3c2f2
  ([#271](https://github.com/n24q02m/better-code-review-graph/pull/271),
  [`270c194`](https://github.com/n24q02m/better-code-review-graph/commit/270c194ced3d385ea4e6e74ba329aa0648248bf8))

- **deps**: Lock file maintenance
  ([#273](https://github.com/n24q02m/better-code-review-graph/pull/273),
  [`fee13b2`](https://github.com/n24q02m/better-code-review-graph/commit/fee13b29e21f16c4c3118d312b0f8c2166c0931d))

- **deps**: Update non-major dependencies
  ([#231](https://github.com/n24q02m/better-code-review-graph/pull/231),
  [`00fdefe`](https://github.com/n24q02m/better-code-review-graph/commit/00fdefed829bebb1ae84a52b74f43d29cd9fa498))

### Chores

- **deps**: Bump cryptography in the uv group across 1 directory
  ([#235](https://github.com/n24q02m/better-code-review-graph/pull/235),
  [`94625e7`](https://github.com/n24q02m/better-code-review-graph/commit/94625e7c634d7ff6381ba938f078f7b2fd2636ec))

- **deps**: Lock file maintenance
  ([#232](https://github.com/n24q02m/better-code-review-graph/pull/232),
  [`12e6acf`](https://github.com/n24q02m/better-code-review-graph/commit/12e6acfd5626bc7698eb59ce54445b07d5d888f6))

- **deps**: Update python:3.13-slim-bookworm docker digest to f13a6b7
  ([#230](https://github.com/n24q02m/better-code-review-graph/pull/230),
  [`f8b4df9`](https://github.com/n24q02m/better-code-review-graph/commit/f8b4df95795f38dbbb0dfa0e9bdd7911b6ab074b))

### Features

- Add coverage tests for get_edges_by_targets batch fetch
  ([`58256d4`](https://github.com/n24q02m/better-code-review-graph/commit/58256d479975a78353fad977f41b70a2f0c36e7c))

- Add cross-OS CI matrix (ubuntu/windows/macos)
  ([`9202f1d`](https://github.com/n24q02m/better-code-review-graph/commit/9202f1d6bef2dfcbd6140d0a9b676c7329b05b1f))

- Add HTTP+OAuth transport, default to HTTP with --stdio fallback
  ([`3b1784a`](https://github.com/n24q02m/better-code-review-graph/commit/3b1784a1304c66ddab6c3cd293086934e8ca9da5))

- Add uv.sources for local mcp-core dev dependency
  ([`0bf7084`](https://github.com/n24q02m/better-code-review-graph/commit/0bf7084b08278c74fad09c7267c981280e358390))

- Migrate from mcp-relay-core to mcp-core
  ([`7a9df64`](https://github.com/n24q02m/better-code-review-graph/commit/7a9df646656a6d863f0515962a249c10f8135cc3))

- Wire save_credentials + apply_config for local OAuth form
  ([`9e93db9`](https://github.com/n24q02m/better-code-review-graph/commit/9e93db9233befa48f932983e0e3a209c45edc970))

### Performance Improvements

- **incremental**: Resolve N+1 query in find_dependents via get_edges_by_targets
  ([#234](https://github.com/n24q02m/better-code-review-graph/pull/234),
  [`654f2b7`](https://github.com/n24q02m/better-code-review-graph/commit/654f2b783692c412859c596e47963cc29ad0beaa))


## v3.8.0 (2026-04-07)

### Bug Fixes

- Add credential state and setup tool tests for relay redesign
  ([`64e18f4`](https://github.com/n24q02m/better-code-review-graph/commit/64e18f42cf4d1a7a8c408f6d74a95f58c076f572))

- Apply ruff formatting and make ty hook non-blocking to match CI
  ([`3d20350`](https://github.com/n24q02m/better-code-review-graph/commit/3d20350fa0aff74fde71cbb14afb03539a2097e6))

- Remove BETA markers and promote relay as primary setup method
  ([`298ad9c`](https://github.com/n24q02m/better-code-review-graph/commit/298ad9c88bb6fd196bfe47a65ef0cdf1ce8ff268))

- Resolve ruff lint errors in agent-generated test files
  ([`31eaeb6`](https://github.com/n24q02m/better-code-review-graph/commit/31eaeb65b9b136bce8167642b3999a1cbe200c75))

- Resolve Windows PermissionError in SQLite test fixtures and lower coverage threshold
  ([`873962f`](https://github.com/n24q02m/better-code-review-graph/commit/873962f90fa5c630370d2494284e79ae86eb5381))

- Sync uv.lock with current version
  ([`44778c2`](https://github.com/n24q02m/better-code-review-graph/commit/44778c2335d8f0b689ab3462f014d436d181fbc0))

### Features

- Migrate code review from Qodo to CodeRabbit
  ([#188](https://github.com/n24q02m/better-code-review-graph/pull/188),
  [`7be7dff`](https://github.com/n24q02m/better-code-review-graph/commit/7be7dfff885a2f115dbd2e6ef3381b2d57b68f36))


## v3.7.2 (2026-04-06)

### Bug Fixes

- Share cloud keys to peer servers when loading from config on startup
  ([`58dd87a`](https://github.com/n24q02m/better-code-review-graph/commit/58dd87a60940ea23e08fbc7dd514c70dd0694e03))


## v3.7.1 (2026-04-06)

### Bug Fixes

- Send complete message to browser after relay and add cross-server sharing
  ([`bc4cdef`](https://github.com/n24q02m/better-code-review-graph/commit/bc4cdef5fe33096cec27429d2ab6a3efcc47111d))


## v3.7.0 (2026-04-06)

### Bug Fixes

- Mark relay as BETA, promote env vars as primary setup method
  ([`f54355f`](https://github.com/n24q02m/better-code-review-graph/commit/f54355ff3eeabd621c50e71b22ec171cb35058f2))

- Resolve lint errors in test files
  ([`c35dc9b`](https://github.com/n24q02m/better-code-review-graph/commit/c35dc9b6e001a5aed2e1b0de86234fa4af590d7f))

### Features

- Non-blocking relay with state machine and lazy trigger
  ([`fb4fa9f`](https://github.com/n24q02m/better-code-review-graph/commit/fb4fa9f2041c6694eeca32a272e7671a3872d521))


## v3.6.0 (2026-04-04)

### Bug Fixes

- Use math.sumprod for cosine similarity and add embedding migration test
  ([#152](https://github.com/n24q02m/better-code-review-graph/pull/152),
  [`963c7df`](https://github.com/n24q02m/better-code-review-graph/commit/963c7df66a592fc32279e860102dcaab2acf2d05))

### Features

- Add agent/manual setup guides, simplify README, cleanup root
  ([`a2ec36c`](https://github.com/n24q02m/better-code-review-graph/commit/a2ec36c6e5fbf23c9bc9c32c1ce4c03bedaafe10))


## v3.5.1 (2026-04-03)

### Bug Fixes

- Harden SQL queries, batch N+1 fetches, add input limits and error tests
  ([#115](https://github.com/n24q02m/better-code-review-graph/pull/115),
  [`4709f66`](https://github.com/n24q02m/better-code-review-graph/commit/4709f66c4d098b9d62d90175f4424a23b8ad10d9))

- Scope marketplace sync token to claude-plugins repo
  ([`dfe45e3`](https://github.com/n24q02m/better-code-review-graph/commit/dfe45e34051eec907edefbf39b97e631071bfd28))


## v3.5.0 (2026-04-03)

### Features

- Remove deprecated Gemini CLI extension support
  ([`20240e2`](https://github.com/n24q02m/better-code-review-graph/commit/20240e2a2af3bf3e2c280457ae2ad03388c38f7b))


## v3.5.0-beta.1 (2026-04-03)

### Features

- Add E2E test infrastructure and consolidated test
  ([`2e69de3`](https://github.com/n24q02m/better-code-review-graph/commit/2e69de3894077f8be0e063442aac120b42a78f63))


## v3.4.0 (2026-04-01)

### Chores

- **deps**: Bump the uv group across 1 directory with 2 updates
  ([#60](https://github.com/n24q02m/better-code-review-graph/pull/60),
  [`1c186ed`](https://github.com/n24q02m/better-code-review-graph/commit/1c186ed8078ebed7067f2ae39ba5df0d0c8a29fb))

### Continuous Integration

- Fix Qodo vertex_ai config and VERTEXAI_LOCATION
  ([`536e15b`](https://github.com/n24q02m/better-code-review-graph/commit/536e15b2fb44b48f0025a347fe49cd5bb059960e))

- **cd**: Add plugin marketplace sync on stable release
  ([`41f09d5`](https://github.com/n24q02m/better-code-review-graph/commit/41f09d5ba17ec5dc72f312309253fdd7ea2383a7))

### Performance Improvements

- **tools**: Replace N+1 queries with batch fetch in `query_graph`
  ([#63](https://github.com/n24q02m/better-code-review-graph/pull/63),
  [`075009b`](https://github.com/n24q02m/better-code-review-graph/commit/075009ba9b3e7c78d719f1fb0236856c6819fa06))


## v3.4.0-beta.1 (2026-03-31)

### Features

- Redesign relay schema with capability-based layout and priority info
  ([`2082258`](https://github.com/n24q02m/better-code-review-graph/commit/2082258316758c0e0a38c6447a5ed2e7aa39c239))


## v3.3.1-beta.1 (2026-03-30)

### Bug Fixes

- **ci**: Pin google-github-actions/auth to SHA v3
  ([`6e5c83d`](https://github.com/n24q02m/better-code-review-graph/commit/6e5c83d6a541429a18fae96852062570774a01a5))

### Chores

- Add Infisical project configuration
  ([`65b03e6`](https://github.com/n24q02m/better-code-review-graph/commit/65b03e6c864987f9c5227e1b45e861ed3c6a57df))

- Remove Infisical config (empty project deleted)
  ([`4d381af`](https://github.com/n24q02m/better-code-review-graph/commit/4d381af335dac4f0186f263471a0eea83d56648a))

### Code Style

- Format relay_setup.py
  ([`c7e7fdf`](https://github.com/n24q02m/better-code-review-graph/commit/c7e7fdf82ba1630e1377ce7ec8db7181e396eda2))

- Format test_relay.py
  ([`bc7100b`](https://github.com/n24q02m/better-code-review-graph/commit/bc7100be20446c6e291d7e8258cba31822a343d1))

### Documentation

- Fix CLAUDE.md discrepancies
  ([`f69f461`](https://github.com/n24q02m/better-code-review-graph/commit/f69f461805306343f7a1d10a16e596db801bcecb))

### Testing

- Update relay tests for multi-provider cloud keys refactor
  ([`ee4ebd8`](https://github.com/n24q02m/better-code-review-graph/commit/ee4ebd8c8a5d65a94e9d36e489ff7ec177abfd49))


## v3.3.0 (2026-03-28)

### Bug Fixes

- Add all 4 embedding providers to relay schema + fix config lookup
  ([`508e959`](https://github.com/n24q02m/better-code-review-graph/commit/508e9599c8ccf55906d6c34678fb55ebbd3bf52f))

- Bump mcp-relay-core to >=1.0.5
  ([`1087881`](https://github.com/n24q02m/better-code-review-graph/commit/10878812cb91758c29805b1d77129418b66a5977))

- Correct relay URL from relay.n24q02m.com to better-code-review-graph.n24q02m.com
  ([`c8c10c8`](https://github.com/n24q02m/better-code-review-graph/commit/c8c10c8a29ef6c32f8f7d4a896ce44826f38c99a))

- Credential resolution order -- relay only when no local credentials
  ([`ed92c21`](https://github.com/n24q02m/better-code-review-graph/commit/ed92c213e06a101eebf8cb4ecd81f08aab045610))

- Increase relay timeout from 30s to 120s
  ([`beb0319`](https://github.com/n24q02m/better-code-review-graph/commit/beb0319d0a64f6b54fe9ca6781dd13be488d63b6))

- Pin Docker base images to SHA digests
  ([`6f48357`](https://github.com/n24q02m/better-code-review-graph/commit/6f483576fb9db320aad7ae32aef19ea05922e279))

- Pin pre-commit hooks to commit SHA
  ([`95dc20d`](https://github.com/n24q02m/better-code-review-graph/commit/95dc20de652682a4fbc8ca5057f9e2f7e429b0ca))

- Send complete message to relay page after config saved
  ([`068419c`](https://github.com/n24q02m/better-code-review-graph/commit/068419c6cf08aaaa25be4a10c90434790d1f2a56))

- **cd**: Remove empty env blocks from OIDC migration
  ([`386d680`](https://github.com/n24q02m/better-code-review-graph/commit/386d680da1cf2c28b1492d7fa8331facc05293e6))

- **cd**: Replace GH_PAT with GitHub App installation token
  ([`46946bd`](https://github.com/n24q02m/better-code-review-graph/commit/46946bd3b38d208fc264c5836dad028ed2c5a8fa))

- **cd**: Use PyPI OIDC trusted publishing instead of PYPI_TOKEN
  ([`31feeb7`](https://github.com/n24q02m/better-code-review-graph/commit/31feeb7b70ae76aa674c871ccaf8e6d0f184f1a5))

- **ci**: Consolidate SMTP_USERNAME and NOTIFY_EMAIL into one secret
  ([`4dcc114`](https://github.com/n24q02m/better-code-review-graph/commit/4dcc11497305d6f95207b0c9d280670b3c4234b4))

- **ci**: Consolidate SMTP_USERNAME+PASSWORD into SMTP_CREDENTIAL
  ([`ef0df19`](https://github.com/n24q02m/better-code-review-graph/commit/ef0df1988c9b96b19cbd3f7e800f69da186bcaa0))

- **ci**: Remove CODECOV_TOKEN, use tokenless upload
  ([`f565418`](https://github.com/n24q02m/better-code-review-graph/commit/f565418dd0422b3db0a700826523622096018a1a))

- **ci**: Use Vertex AI WIF instead of GEMINI_API_KEY for code review
  ([`9e19886`](https://github.com/n24q02m/better-code-review-graph/commit/9e19886575254089d3f6ee59ecec009d1beb898c))

- **deps**: Update non-major dependencies
  ([#41](https://github.com/n24q02m/better-code-review-graph/pull/41),
  [`f365b16`](https://github.com/n24q02m/better-code-review-graph/commit/f365b163ef3a5fd69b263d0f40cbd860406d9243))

- **tests**: Keep embedding mock active during semantic search tests
  ([`2942dec`](https://github.com/n24q02m/better-code-review-graph/commit/2942dec9be71076e055e85362b60a2b512bc1dbe))

- **tests**: Mock embedding backend instead of skipping tests
  ([`2e33242`](https://github.com/n24q02m/better-code-review-graph/commit/2e33242008b0dcad644f1a6ded2567f8bb746dec))

- **tests**: Remove unused top-level os import (ruff F401)
  ([`6b3fdf6`](https://github.com/n24q02m/better-code-review-graph/commit/6b3fdf61ef02823fdaee10487ec199973cf40bdd))

- **tests**: Skip embedding tests when no API key available
  ([`4e75a43`](https://github.com/n24q02m/better-code-review-graph/commit/4e75a437f707bb3cb6f06688b360e4475a6c2990))

- **tests**: Update mock paths for lazy-imported relay functions
  ([`f154e1e`](https://github.com/n24q02m/better-code-review-graph/commit/f154e1e8d47fdcafe53f9a1b31fbd4f1bdac0cf5))

### Chores

- Add .env to .gitignore for secret protection
  ([`c17560f`](https://github.com/n24q02m/better-code-review-graph/commit/c17560faf97161965674817793911bba9a488e50))

- **deps**: Update actions/create-github-app-token action to v3
  ([#47](https://github.com/n24q02m/better-code-review-graph/pull/47),
  [`2413aca`](https://github.com/n24q02m/better-code-review-graph/commit/2413aca5a9092435d25cde89c2b4c16d22167db3))

- **deps**: Update codecov/codecov-action action to v6
  ([#48](https://github.com/n24q02m/better-code-review-graph/pull/48),
  [`6c466be`](https://github.com/n24q02m/better-code-review-graph/commit/6c466be8f23dfcf27b1b74f1c95f51d326382113))

- **deps**: Update github/codeql-action digest to 5c8a8a6
  ([#45](https://github.com/n24q02m/better-code-review-graph/pull/45),
  [`16b0bcb`](https://github.com/n24q02m/better-code-review-graph/commit/16b0bcbbe849792186f25c91380085f183dc9c9b))

### Code Style

- Format test_coverage_gaps.py
  ([`79442c3`](https://github.com/n24q02m/better-code-review-graph/commit/79442c3f5dbb28393aa469f93ecbbaff8196f734))

### Continuous Integration

- Retrigger CI (ruff cache issue)
  ([`719162b`](https://github.com/n24q02m/better-code-review-graph/commit/719162bd1fa7f3f509c3bdeb9576e3ccd335ac2a))

### Features

- Relay-first startup — always show relay URL
  ([`4d9ccea`](https://github.com/n24q02m/better-code-review-graph/commit/4d9cceab4018d90f4b9a1339d74e38b63dbe86a3))

### Testing

- Fix relay test assertions to match implementation
  ([`50cdc87`](https://github.com/n24q02m/better-code-review-graph/commit/50cdc87fd7917c61efddec5bc0b514e08db6cd24))

- Improve coverage to meet 95% threshold
  ([`84a0e92`](https://github.com/n24q02m/better-code-review-graph/commit/84a0e92420ee4faadd65c4b5c94aa29649c88940))


## v3.2.0 (2026-03-26)

### Chores

- Add server.json to PSR version_variables, sync version
  ([`d6a1cde`](https://github.com/n24q02m/better-code-review-graph/commit/d6a1cdeb294570a8beb3c38bbabac122fc7b8195))

- Clean up plugin manifest for best practices
  ([`db9d65b`](https://github.com/n24q02m/better-code-review-graph/commit/db9d65b5171434ce633ffa910a8a09c68357c623))

### Documentation

- Fix marketplace references, improve Gemini CLI extension config
  ([`b6bc8c2`](https://github.com/n24q02m/better-code-review-graph/commit/b6bc8c2b85127b0bf53a22239dc61b1c5384b878))

- Standardize README structure
  ([`ee9b10f`](https://github.com/n24q02m/better-code-review-graph/commit/ee9b10fcc1b43426912b1592c8389c104871ad80))


## v3.2.0-beta.1 (2026-03-25)

### Bug Fixes

- Switch mcp-relay-core from git dep to published PyPI package
  ([#36](https://github.com/n24q02m/better-code-review-graph/pull/36),
  [`2147030`](https://github.com/n24q02m/better-code-review-graph/commit/214703007fc43961201c8a8387535d6eda6f2f4e))

### Documentation

- Add relay files to CLAUDE.md file structure
  ([`e335e48`](https://github.com/n24q02m/better-code-review-graph/commit/e335e48b3ca494883dd69975f7f7bebc80a4d321))

- Add zero-config relay setup section to README
  ([`af7ddac`](https://github.com/n24q02m/better-code-review-graph/commit/af7ddac4e18458c54899ac920d4e50502340b9f5))

### Features

- Integrate mcp-relay-core for zero-env-config setup
  ([#36](https://github.com/n24q02m/better-code-review-graph/pull/36),
  [`2147030`](https://github.com/n24q02m/better-code-review-graph/commit/214703007fc43961201c8a8387535d6eda6f2f4e))

- Zero-env-config relay setup via mcp-relay-core
  ([#36](https://github.com/n24q02m/better-code-review-graph/pull/36),
  [`2147030`](https://github.com/n24q02m/better-code-review-graph/commit/214703007fc43961201c8a8387535d6eda6f2f4e))


## v3.1.0 (2026-03-25)

### Bug Fixes

- Add 'docs/' to .gitignore
  ([`de96b38`](https://github.com/n24q02m/better-code-review-graph/commit/de96b38db092074c5c9bc1df8e0b9bea33ef7944))

- Delete docs directory
  ([`a8b38b9`](https://github.com/n24q02m/better-code-review-graph/commit/a8b38b907b6b745e2c70658cd74d68c6aa5c9e3d))

- Update README for embedding cloud description
  ([`5756798`](https://github.com/n24q02m/better-code-review-graph/commit/5756798ef68336784fe694261a40263981d660ef))


## v3.1.0-beta.2 (2026-03-25)

### Bug Fixes

- Replace LiteLLM references with Cohere cloud in docs
  ([`a2ccb40`](https://github.com/n24q02m/better-code-review-graph/commit/a2ccb40ca1766a21ccd83265b9f3d03e3e760090))

- Update AGENTS.md/CLAUDE.md — remove litellm references
  ([`5027710`](https://github.com/n24q02m/better-code-review-graph/commit/50277103cd42a76af63935ad6c3b7d486cc4fca2))

- Update docs — remove litellm references, add multi-provider info
  ([`eb91c46`](https://github.com/n24q02m/better-code-review-graph/commit/eb91c460c8c916b93cf43a2a01f80a77f7ec0a32))

### Features

- Upgrade to multi-provider embedding (jina > gemini > openai > cohere)
  ([`849b193`](https://github.com/n24q02m/better-code-review-graph/commit/849b193ac323a9033295282f543ab83eaa50aead))


## v3.1.0-beta.1 (2026-03-25)

### Bug Fixes

- Auto-sync plugin.json version via PSR
  ([`f96baf3`](https://github.com/n24q02m/better-code-review-graph/commit/f96baf306dbbc089f997c862b0cce194db8cf3b5))

- Correct plugin install commands per official docs
  ([`c8e6826`](https://github.com/n24q02m/better-code-review-graph/commit/c8e6826ac04a8a6371c940bd216057f13266881b))

- Pin third-party GitHub Actions to SHA hashes
  ([`3065f82`](https://github.com/n24q02m/better-code-review-graph/commit/3065f8219d763761d14cb5c74a0cc8f7d97c87cc))

- Remove empty env vars from plugin configs to prevent empty-string bugs
  ([`645b7aa`](https://github.com/n24q02m/better-code-review-graph/commit/645b7aa6377b9c464be41501b4e56487eb57cc0d))

- Remove env vars from plugin.json to prevent overwriting user config
  ([`6949438`](https://github.com/n24q02m/better-code-review-graph/commit/6949438cfc8af70e1ff7d3df08aa2ae1c072d11c))

- Remove invalid hooks field from plugin.json
  ([`43dc3f8`](https://github.com/n24q02m/better-code-review-graph/commit/43dc3f89792ca7ac9e2cd1cc1c32d4cdce741bf6))

- Remove pr-title-check job from CI
  ([`f287d23`](https://github.com/n24q02m/better-code-review-graph/commit/f287d233c8559b29c740bf071b326e147036e475))

- Replace non-existent build-graph skill with refactor-check in README
  ([`7a8fde5`](https://github.com/n24q02m/better-code-review-graph/commit/7a8fde558d3676c61e9534d2440a6be77cc24f0f))

- Split PSR version_toml — move JSON files to version_variables
  ([`86203ab`](https://github.com/n24q02m/better-code-review-graph/commit/86203aba96bdf01712bbce4daab0a613bd7842b1))

- Sync plugin.json version and add skills/hooks references
  ([`a6d3aca`](https://github.com/n24q02m/better-code-review-graph/commit/a6d3acabc85d60b1d602f4ee34eeb403a3bce596))

- Sync uv.lock with native provider SDK dependencies
  ([`c1c428e`](https://github.com/n24q02m/better-code-review-graph/commit/c1c428ed062e1e5409564c4bc3c979bf97a917ba))

- Unify Plugin install section with marketplace + individual options
  ([`b885614`](https://github.com/n24q02m/better-code-review-graph/commit/b885614e37e56c131fc813589fcaee188ee53432))

- Update ruff pre-commit hook to v0.15.7
  ([`d00ee2e`](https://github.com/n24q02m/better-code-review-graph/commit/d00ee2ede5a101331e15d0235a98549017b5a23a))

### Features

- Add complete env vars and pipx mode to plugin config
  ([`d66b9f8`](https://github.com/n24q02m/better-code-review-graph/commit/d66b9f84188e3136f68493d0d236aaf5255cb825))

- Add EMBEDDING_MODEL and EMBEDDING_BACKEND to plugin config
  ([`4023941`](https://github.com/n24q02m/better-code-review-graph/commit/40239414a71508527fd3070e043cfd33fe9009d8))

- Add Gemini CLI extension config
  ([`d088418`](https://github.com/n24q02m/better-code-review-graph/commit/d088418c505596bc15c8543a9e047c492e20e55a))

- Multi-mode plugin config (stdio + docker + http)
  ([`a2daaf7`](https://github.com/n24q02m/better-code-review-graph/commit/a2daaf7f602ddeffbd5ed03186436b5c115b9cb1))

- Standardize README with MCP Resources, Security, collapsible clients
  ([`5d0c794`](https://github.com/n24q02m/better-code-review-graph/commit/5d0c794828a36f55a064fa8a6b65f972e7e0b552))

### Refactoring

- Replace LiteLLM embedding with Cohere SDK (embed-multilingual-v3.0)
  ([`cc444cc`](https://github.com/n24q02m/better-code-review-graph/commit/cc444cc7f6ab2a00e5b0bb74741c2337b15d36f8))


## v3.0.0 (2026-03-24)

### Bug Fixes

- Add gitleaks secret detection to pre-commit hooks
  ([`7253163`](https://github.com/n24q02m/better-code-review-graph/commit/72531632ad724e44a3aa878cb27a30c33b4c748e))

- Apply ruff formatting to pass CI
  ([`be854ce`](https://github.com/n24q02m/better-code-review-graph/commit/be854ce28e84d37959746c57785662df727b4126))

- Fix Bandit B608 SQL Injection warnings in graph queries
  ([#3](https://github.com/n24q02m/better-code-review-graph/pull/3),
  [`efe5dc7`](https://github.com/n24q02m/better-code-review-graph/commit/efe5dc719200e06d71269fcf4dc97d3e62b7e05c))

- Move imports before pytestmark to fix ruff E402
  ([`01c1e64`](https://github.com/n24q02m/better-code-review-graph/commit/01c1e6420439dc7abb02bf5c2ec468d7e26e3445))

- Remove .jules/bolt.md from PR ([#4](https://github.com/n24q02m/better-code-review-graph/pull/4),
  [`005f2ea`](https://github.com/n24q02m/better-code-review-graph/commit/005f2eac5af21d24c7ffb38ac34055f868daeedc))

### Features

- Optimize cosine similarity calculation
  ([#4](https://github.com/n24q02m/better-code-review-graph/pull/4),
  [`005f2ea`](https://github.com/n24q02m/better-code-review-graph/commit/005f2eac5af21d24c7ffb38ac34055f868daeedc))

### Performance Improvements

- Optimize _cosine_similarity with math.hypot and map
  ([#4](https://github.com/n24q02m/better-code-review-graph/pull/4),
  [`005f2ea`](https://github.com/n24q02m/better-code-review-graph/commit/005f2eac5af21d24c7ffb38ac34055f868daeedc))

### Testing

- Add cloud embedding mode tests with API_KEYS
  ([`864b483`](https://github.com/n24q02m/better-code-review-graph/commit/864b483ad8270b105a70fc508f4ec33ac4e86297))

- Add full/real live tests for all query patterns and modes
  ([`38f546a`](https://github.com/n24q02m/better-code-review-graph/commit/38f546a0749984e357fe1be03702fb322ee1045d))


## v3.0.0-beta.1 (2026-03-23)

### Bug Fixes

- Add missing .github config files for consistency
  ([`5271449`](https://github.com/n24q02m/better-code-review-graph/commit/5271449a9835c7f6b9b989b412ec0b547b94653a))

- Add PSR config, fix Semgrep false positives, sync server.json
  ([`c6af422`](https://github.com/n24q02m/better-code-review-graph/commit/c6af4223c60d98fdb321fcb092d89d3654d8664d))

- Format cli.py and test_cli.py with ruff
  ([`cd70342`](https://github.com/n24q02m/better-code-review-graph/commit/cd70342d8370110b309906e8892b196e1e2b91fb))

- Improve tool descriptions and corrective errors for LLM call pass rate
  ([`5774f90`](https://github.com/n24q02m/better-code-review-graph/commit/5774f90f8e6e99218e21c682af0ca29261a64fc6))

- Remove stale 'serve' arg from live MCP test server params
  ([`30c9415`](https://github.com/n24q02m/better-code-review-graph/commit/30c9415c548bf64bd1b5a6d8038889efbec79302))

- Remove stale 'serve' from plugin.json args, fix plugin add command
  ([`beff261`](https://github.com/n24q02m/better-code-review-graph/commit/beff261d37cb4502b45587b1ffe2e4afcf0ebb64))

- Replace encoding_format with drop_params in LiteLLM calls
  ([`d8739cd`](https://github.com/n24q02m/better-code-review-graph/commit/d8739cd4a1a70e45a215b60871336559a97fafd6))

- Standardize README structure
  ([`1f10fb8`](https://github.com/n24q02m/better-code-review-graph/commit/1f10fb85c2da1d19df9f5f3fbe4236ee51cbb802))

- Update session-start.sh to reference MCP tool instead of deleted skill
  ([`8339cb9`](https://github.com/n24q02m/better-code-review-graph/commit/8339cb91a202e9bcd95d71701e4c5a44b9823bd0))

### Chores

- Add renovate.json, community docs, fix server.json env vars
  ([`e3b7f4c`](https://github.com/n24q02m/better-code-review-graph/commit/e3b7f4c1193cb9cdaa15316d4d8e7bb091c79cdf))

- **release**: Bump version to 2.0.0
  ([`9973177`](https://github.com/n24q02m/better-code-review-graph/commit/99731776f062d460e672e2c52b4287b9f93d9d63))

### Continuous Integration

- Replace Semgrep with CodeQL for SAST scanning
  ([`e6842b4`](https://github.com/n24q02m/better-code-review-graph/commit/e6842b4d98b7d504da0d7eb23905686bf93a5a0f))

### Documentation

- Add Solidity to Supported Languages in README
  ([`a8b2554`](https://github.com/n24q02m/better-code-review-graph/commit/a8b25549fdadc586fb8f84b727740670588de953))

- Standardize README sections and sync Also by table
  ([`b72e13a`](https://github.com/n24q02m/better-code-review-graph/commit/b72e13ae679e623e784761809e0ce1970e7c924d))

- Update CLAUDE.md to reflect 13 supported languages (add Solidity)
  ([`c1e4b7a`](https://github.com/n24q02m/better-code-review-graph/commit/c1e4b7a286e0f6956d2d17746d5760753b19426f))

- Update CLAUDE.md to reflect CLI serve default
  ([`7046181`](https://github.com/n24q02m/better-code-review-graph/commit/7046181aa8388a1f811d4703f46b3c50d35c9234))

### Refactoring

- Make serve the default CLI command, remove serve subcommand
  ([`b60933a`](https://github.com/n24q02m/better-code-review-graph/commit/b60933aff8b48f8c0b803361d7dfe649807a6170))

- Migrate update CLI to MCP-only, fix PostToolUse hook
  ([`f67b9e7`](https://github.com/n24q02m/better-code-review-graph/commit/f67b9e778ebaf33c880b8db2ef6beca060c1a306))

- Redesign skills per approved spec
  ([`d3baa4f`](https://github.com/n24q02m/better-code-review-graph/commit/d3baa4f4f26f18d853cb8c838cdc181230acbc38))

- Split graph mega-tool into 5-tool architecture
  ([`7276209`](https://github.com/n24q02m/better-code-review-graph/commit/72762098c50b699c9cf24f9ddcce71bfaa320076))

### Testing

- Add missing live MCP protocol tests for graph update, config cache_clear, and error paths
  ([`4e76e9a`](https://github.com/n24q02m/better-code-review-graph/commit/4e76e9a5bebc48bf2bb7d4d2d4d0dd6ab69fdf14))


## v2.0.0 (2026-03-20)

### Bug Fixes

- Add remote type to PSR config for version commit push
  ([`34327d9`](https://github.com/n24q02m/better-code-review-graph/commit/34327d96691355086394aad18fe49a004ed50016))

- Add ty to dev deps, nosemgrep for importlib.resources
  ([#1](https://github.com/n24q02m/better-code-review-graph/pull/1),
  [`03a5118`](https://github.com/n24q02m/better-code-review-graph/commit/03a5118f913f71d9a4e63082c8b619994f9e4610))

### Chores

- Add .worktrees/ to gitignore
  ([`75d3154`](https://github.com/n24q02m/better-code-review-graph/commit/75d315423d073d8e2c7d64665f8c94d15f1d4fca))

### Continuous Integration

- Fix ty missing from dev deps, make ty non-fatal
  ([#1](https://github.com/n24q02m/better-code-review-graph/pull/1),
  [`03a5118`](https://github.com/n24q02m/better-code-review-graph/commit/03a5118f913f71d9a4e63082c8b619994f9e4610))

### Documentation

- Rewrite README with 3-tier tools, per-agent install guides
  ([#1](https://github.com/n24q02m/better-code-review-graph/pull/1),
  [`03a5118`](https://github.com/n24q02m/better-code-review-graph/commit/03a5118f913f71d9a4e63082c8b619994f9e4610))

- Update CLAUDE.md, AGENTS.md, skills for 3-tier tools
  ([#1](https://github.com/n24q02m/better-code-review-graph/pull/1),
  [`03a5118`](https://github.com/n24q02m/better-code-review-graph/commit/03a5118f913f71d9a4e63082c8b619994f9e4610))

### Features

- Add docs/ directory for help tool (graph.md, config.md)
  ([#1](https://github.com/n24q02m/better-code-review-graph/pull/1),
  [`03a5118`](https://github.com/n24q02m/better-code-review-graph/commit/03a5118f913f71d9a4e63082c8b619994f9e4610))

- Refactor 9 tools into 3-tier architecture (graph + config + help)
  ([#1](https://github.com/n24q02m/better-code-review-graph/pull/1),
  [`03a5118`](https://github.com/n24q02m/better-code-review-graph/commit/03a5118f913f71d9a4e63082c8b619994f9e4610))

- Simplify CLI to serve + update only
  ([#1](https://github.com/n24q02m/better-code-review-graph/pull/1),
  [`03a5118`](https://github.com/n24q02m/better-code-review-graph/commit/03a5118f913f71d9a4e63082c8b619994f9e4610))

- V2 — 3-tier tool architecture (graph + config + help)
  ([#1](https://github.com/n24q02m/better-code-review-graph/pull/1),
  [`03a5118`](https://github.com/n24q02m/better-code-review-graph/commit/03a5118f913f71d9a4e63082c8b619994f9e4610))

### Testing

- Add Phase 5 live MCP protocol integration tests
  ([`b5f46f0`](https://github.com/n24q02m/better-code-review-graph/commit/b5f46f080e639837bbd082727dfd66214bad9d02))

- Improve coverage for config/help tools, lint fixes
  ([#1](https://github.com/n24q02m/better-code-review-graph/pull/1),
  [`03a5118`](https://github.com/n24q02m/better-code-review-graph/commit/03a5118f913f71d9a4e63082c8b619994f9e4610))


## v1.0.3 (2026-03-20)

### Bug Fixes

- Add MCP Registry LABEL to Dockerfile for OCI validation
  ([`333efe3`](https://github.com/n24q02m/better-code-review-graph/commit/333efe393770d2b57f1f8b5e99b61c34d32baa28))


## v1.0.2 (2026-03-20)

### Bug Fixes

- Decouple MCP Registry publish from PyPI in CD workflow
  ([`050d180`](https://github.com/n24q02m/better-code-review-graph/commit/050d1803ea34ffeefaba983eddc956226e92bea5))


## v1.0.1 (2026-03-20)

### Bug Fixes

- Correct server.json schema for MCP Registry (identifier, transport)
  ([`4c615fc`](https://github.com/n24q02m/better-code-review-graph/commit/4c615fca8e716242682b02361f8f0a863f21c347))


## v1.0.0 (2026-03-20)

### Chores

- **release**: Sync version to 1.0.0b2 to match PSR tag
  ([`ab920e8`](https://github.com/n24q02m/better-code-review-graph/commit/ab920e85d57d55fcd49eef56baba04d8adae4845))


## v1.0.0-beta.2 (2026-03-20)

### Bug Fixes

- Include README.md in Docker build for hatchling
  ([`03264e1`](https://github.com/n24q02m/better-code-review-graph/commit/03264e12c3c1788a492756a8c116972f85077383))


## v1.0.0-beta.1 (2026-03-20)

- Initial Release
