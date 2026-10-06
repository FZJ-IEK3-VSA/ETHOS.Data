# Errors

Every refusal `ethos_data` raises on purpose is an
[`EthosDataError`][ethos_data.errors.EthosDataError]. Library code raises it and
never exits the process, so a script, a test and the command line all receive
the same exception. Each class also derives from the standard exception that
describes it, so an `except KeyError` catches an unknown name and an
`except OSError` an unreadable catalogue. Import them from `ethos_data` or
`ethos_data.errors`.

The command line prints a refusal as `error: <message>` and exits with the
error's `exit_code`:

| Exit | Errors | Means |
|---|---|---|
| `2` | everything below except the maintenance errors | the request could not be served: an unknown name, an unreadable catalogue, data this machine cannot read, an invalid collection, bundle or setting, a refused staging entry |
| `1` | [`MaintenanceError`][ethos_data.errors.MaintenanceError] and its subclasses | a `catalog` command refused its input: a descriptor the build rejects, a checkout that is not a source catalogue, an upload or a publication that cannot go ahead, a step the dataset's state does not allow |

A command can also return `1` for a finding rather than a refusal, a stale
`build --check` or a failed `verify`, as its reference page describes.

::: ethos_data.errors
    options:
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 2
      members_order: source
