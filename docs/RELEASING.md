# Releasing

Checklist for maintainers publishing a new version of the Charlotte AI AgentWorks Skills plugin.
This is a maintainer-only task — contributors don't need to do any of this to get a PR merged.

1. Bump the version in `plugin.json` and `.codex-plugin/plugin.json`. Keep the two in sync.
2. Update the marketplace manifests:
   - `.claude-plugin/marketplace.json` — bump `plugins[].version`.
   - `.agents/plugins/marketplace.json` (Codex-style marketplace) — bump `plugins[].version` and
     `plugins[].source.ref` to `vX.Y.Z`.
3. Add a dated entry to [`CHANGELOG.md`](../CHANGELOG.md) summarizing the release, and add the
   corresponding `[X.Y.Z]: .../releases/tag/vX.Y.Z` link at the bottom of the file.
4. Commit the version bump and merge it into `main`.
5. Tag and push the release:
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
