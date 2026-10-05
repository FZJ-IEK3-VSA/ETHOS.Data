# 10. Quality Requirements

This chapter makes the quality goals of [section 1](introduction-and-goals.md)
checkable: each goal is broken down into scenarios, and each scenario names the
test or check that shows it holds.

## 10.1 Quality tree

The tree assigns each scenario of [section 10.2](#102-quality-scenarios) to the
goal it tests. A scenario is a review and test criterion, not a measured
performance guarantee.

<figure markdown="span">
  ![Quality tree: six quality goals, each with the scenarios that test it. Traceable, repeatable inputs: Q2, Q9, Q10, Q17, Q21. Controlled access and publication: Q3, Q4, Q13. Reuse and availability: Q1, Q8. Safe maintenance and diagnosis: Q6, Q7, Q11, Q12, Q18, Q19. Scalable metadata access: Q5. Changeable code: Q14, Q15, Q16, Q20.](../../assets/diagrams/architecture-quality-light.svg#only-light){ .diagram }
  ![Quality tree: six quality goals, each with the scenarios that test it. Traceable, repeatable inputs: Q2, Q9, Q10, Q17, Q21. Controlled access and publication: Q3, Q4, Q13. Reuse and availability: Q1, Q8. Safe maintenance and diagnosis: Q6, Q7, Q11, Q12, Q18, Q19. Scalable metadata access: Q5. Changeable code: Q14, Q15, Q16, Q20.](../../assets/diagrams/architecture-quality-dark.svg#only-dark){ .diagram }
</figure>

## 10.2 Quality scenarios

An acceptance check names the tests that show the response, by file and test
name in `tests/`, or describes the check.

| ID | Trigger and environment | Expected response | Acceptance check |
|---|---|---|---|
| Q1 | Two packages select the same resource under the same public cache | Both derive the same path from the resource key, and a valid download is reused | `test_downloads.py`: `test_a_file_already_in_the_cache_is_not_downloaded_again` |
| Q2 | A downloaded file in a user's public cache is corrupt | The hash check refuses it as a cache hit, and retrieval downloads it again: the lookup chain takes a copy only at its recorded size, and the Downloader keeps a present file only when its SHA-256 matches | `test_lookup_chain.py`: `test_a_copy_of_the_recorded_size_is_used_and_any_other_is_replaced`; `test_adapters.py`: `test_pooch_refuses_bytes_that_do_not_match` |
| Q3 | A required restricted dataset has no installation this account can read | The call fails before anything is downloaded, describing the dataset and how to register a copy; `plan()` reports it as not available here | `test_required_inputs.py`: `test_it_describes_the_dataset_and_how_to_register_a_copy`, `test_a_plan_lists_it_as_not_available_here` |
| Q4 | Internal metadata holds hidden datasets and unpublished keys | The public view leaves them out, and the leak check refuses a tree that still holds one | `test_publish.py`: `test_a_hidden_dataset_is_never_named`, `test_maintainer_bookkeeping_is_stripped`, `test_a_tree_that_names_a_withheld_dataset_is_not_written` |
| Q5 | A caller loads an index with large inventories | Only the descriptors and shards a request needs are read | A request for one file of a sharded dataset reads the index, that dataset's descriptor and the one shard that can hold the file. `test_bundles.py`: `test_subset_export_never_loads_unselected_shards` |
| Q6 | A later dataset in an upload batch fails its checks | No dataset of the batch starts transferring | `test_upload_subset.py`: `test_a_restricted_dataset_stops_the_run_before_its_neighbour_uploads` |
| Q7 | A dataset's build input holds files its inventory excludes | Only the inventory's files are transferred | `test_adapters.py`: `test_a_copy_transfers_exactly_the_inventory_and_never_overwrites` |
| Q8 | Required tests run in a fresh checkout, with an empty cache and no network | The repository bundles supply every input and its metadata; a missing or changed file fails without fallback | Every test runs with the network blocked (`conftest.py`). A handle built from its bundles alone, with no catalogue index reachable, returns every input. `test_repository_bundles.py`: `test_an_altered_bundled_file_is_an_error_not_a_download` |
| Q9 | A developer changes a bundled file to reproduce a bug | The read is refused until `bundle update` records the change, or it is read with `allow_modified` and a warning, while the recorded hashes and dCache stay as they are | `test_repository_bundles.py`: `test_an_altered_bundled_file_is_an_error_not_a_download`; `test_bundles.py`: `test_development_override_reports_changes_and_preserves_hashes` |
| Q10 | A package reruns a collection bounded to an older release of the public catalogue | Selection keeps the same keys, and the published objects, a revision's folder included, match the recorded hashes. On the cluster, which serves the latest internal release only, a collections file whose bounds exclude that release is refused with `CatalogVersionError`. | `test_catalogue_versions.py`: `test_exact_version_reads_that_release`, `test_one_outside_them_is_refused_naming_both`; `test_revisions.py`: `test_a_reader_keeps_the_revision_beside_the_one_before`. Limited by host retention ([section 11](risks-and-technical-debt.md)). |
| Q11 | A maintainer takes a step the dataset's state does not allow, such as uploading a draft or a frozen dataset | The command refuses before it changes anything and names what the dataset needs first | `test_status_files.py`: `test_a_step_the_state_does_not_allow_says_what_comes_first`, `test_a_frozen_dataset_is_only_rechecked` |
| Q12 | A release, a removal or a purge is interrupted and run again | The rerun does only what is left; nothing already done is done again | `test_release.py`: `test_running_it_again_finishes_what_is_left`; `test_pipelines.py`: `test_removing_again_withdraws_nothing_new`. A purge run again after an interruption purges only the revision folders the store still holds. |
| Q13 | A maintainer purges a withdrawn dataset | Nothing is deleted until a release without the dataset is recorded, and the name stays taken | `test_release.py`: `TestPurge`, among them `test_it_waits_for_a_release_without_the_dataset` and `test_a_purged_name_is_not_given_to_other_bytes` |
| Q14 | A key is added to a file format | Validation, the schema, the templates' checks and the reference table change with the model; a stale committed schema fails a test | `test_formats.py`: `test_the_committed_schemas_are_current`; `test_reference.py`: `test_every_key_of_a_format_has_a_described_row` |
| Q15 | Library code imports a layer above its own | A test fails, naming the module and the import | `test_layers.py`: `test_a_module_imports_nothing_above_its_layer` |
| Q16 | A shard is missing from a checkout or a published tree | The one inventory reader finds it for both sides, and both name the same dataset, part and location: a handle raises `IncompleteCatalog`, and a maintainer command adds the `catalog build` to run. Maintainers see the resources readers see. | One in-memory tree with a shard missing, read by a handle and by a maintainer command, gives both messages the same facts. `test_variants_and_named_paths.py`: `test_a_missing_shard_is_diagnosed_the_same_way` covers the handle. |
| Q17 | A script asks for paths with `fetch=False` on a machine that lacks a file | No store is contacted; `NotFetched` names each file and the path it belongs at | `test_lookup_chain.py`: `test_a_missing_file_is_named_with_the_path_it_belongs_at`, `test_a_file_that_is_here_is_returned_without_asking_the_store` |
| Q18 | A user runs `report` | The report holds no token, no credential in a URL, no home path and no account name | `test_handoffs.py`: `test_a_report_is_scrubbed`, `test_the_report_holds_the_facts_without_personal_paths` |
| Q19 | A maintainer runs any `catalog` command with `--dry-run` | No file, git ref or store object changes; the store is only read | `test_pipelines.py`: `test_a_dry_run_is_the_plan`, and a dry-run case for each command. Every pipeline, `upload` and `publish` included, runs its dry run against the fakes, which record no write. |
| Q20 | A data-access module imports `ethos_data.maintain` | A test fails, naming the import | The layer test (`test_layers.py`) also checks the two service groups: a data-access module that imports catalogue maintenance fails it. |
| Q21 | The environment or the settings file changes after a handle was built | The handle keeps the catalogue and roots it started with, and `print(handle.settings)` names every source | `test_settings_file.py`: `test_it_is_read_once_so_later_changes_do_not_move_the_cache`, `test_it_names_the_file_the_catalogue_and_the_caches` |

## 10.3 Measurement boundaries

Lazy loading is a mechanism, not a measured target. Latency, memory and
concurrency targets need agreed workloads, and an agreed machine and storage
environment, before numbers can be set. Remote verification checks
reachability and size, not content. The risks that follow are in
[section 11](risks-and-technical-debt.md).
