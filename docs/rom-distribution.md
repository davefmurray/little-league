# ROM distribution policy

The base ROM is Nintendo-copyrighted and is **not** in this repository.
`build/` is gitignored, including `build/direct31.nes` and every intermediate.

## Policy

- **Do not host or attach the patched ROM.** Serve the patch/IPS (or the
  build scripts + data) instead.
- The hosted editor lets a user load their own ROM in the browser; the ROM
  stays local and is not uploaded.
- CI artifacts must not include the ROM; the tests use synthetic fixtures or
  a locally supplied base.
- Documentation may show screenshots and checksums, not the ROM bytes.
- If a download is requested, provide a **patch file** and require the user
  to supply the base ROM.

This keeps the project in the same posture as the existing docs: data,
tools, patches, and screenshots only.
