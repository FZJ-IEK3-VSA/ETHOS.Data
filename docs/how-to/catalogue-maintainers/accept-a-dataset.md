# Accept a dataset proposal

Review a package maintainer's [proposal](../package-maintainers/propose-a-dataset.md) in a private
source-catalogue checkout with access to stable candidate bytes.

1. **Review the submission.** Confirm identity, provenance, licensing,
   visibility, selection and validation. Agree on new paths for changed
   published bytes and preserve paths needed by existing pins.
2. **Describe and build.** Follow [Describe a dataset](describe-a-dataset.md).
   Set `source_dir` to the candidate location you can actually read. Compare
   generated paths, sidecars, sizes and hashes with the submission; resolve
   unexpected differences before proceeding.
3. **Establish byte availability.** For public data, follow
   [Upload and verify](upload-a-dataset.md). For restricted or local internal
   data, [register and verify its installation](link-cluster-data.md).
   Restricted data has no upload step. A later subset-transfer failure does
   not roll back earlier transfers.
4. **Record the authoritative copy.** Only after successful upload/verification,
   set `ethos:uploaded: true`, remove `source_dir` and rebuild. For local
   installations, retain their source or follow the
   [frozen-inventory procedure](link-cluster-data.md#retire-the-original).
5. **Release metadata.** [Generate and review the public view](publish-the-catalogue.md),
   then [deploy complete, versioned metadata](catalogue-hosting.md). Making a
   downloadable entry available to consumers follows successful upload and
   verification; local metadata generation alone does not prove storage readiness.
6. **Complete the handoff.** Give the contributor accepted dataset identifiers
   and a catalogue revision to pin. Ask them to remove development overrides and
   verify the package workflow. Keep proposal, validation and release identifiers
   together.

These are coordinated maintainer actions; the CLI does not perform a transaction
across dCache, Git hosts and cluster deployment. See
[catalogue CI checks](catalogue-ci.md) and [diagnostics](../data-users/troubleshoot-catalogue.md).
