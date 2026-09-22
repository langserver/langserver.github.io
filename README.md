# langserver.github.io

Managed by [Sourcegraph](https://sourcegraph.com).

Please file issues or submit pull requests for any additions, suggestions, or corrections in this repository.

## Validation

Run the project-specific table layout checks locally with:

```sh
python3 scripts/validate_tables.py
```

The validator checks the server and client tables' headers, row widths, cell order, capability
statuses, repository links, check icons, and Work in Progress section rows. CI runs it for every
pull request.
