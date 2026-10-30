# ROM distribution policy

The original game's ROM is **not** in this repository.
`build/` is gitignored, including `build/direct31.nes` and every intermediate.

## Policy

- **Do not commit or bake a ROM into the repository or the Docker image.**
- The project owner publishes the 32-team preview builds as assets of the
  `32-team-preview-N` GitHub releases. The README and the editor link only
  the pinned [Preview 8 asset](https://github.com/davefmurray/little-league/releases/tag/32-team-preview-8),
  the one 32-team build the editor opens. Do not publish ROMs through any
  other channel; for other builds, serve the patch/IPS (or the build scripts
  + data).
- The hosted editor never serves, proxies or stores a ROM. A user downloads
  the release asset or uses their own dump, then opens it in the browser;
  the ROM stays local and is not uploaded. The server's `/rom` route is for
  loopback development only and is disabled when hosted.
- CI artifacts must not include the ROM; the tests use synthetic fixtures or
  a locally supplied base.
- Documentation may show screenshots and checksums, not the ROM bytes.

Apart from those release assets, the project publishes data, tools,
patches, and screenshots only.
