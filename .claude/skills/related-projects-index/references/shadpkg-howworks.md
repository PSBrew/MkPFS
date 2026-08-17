# ShadPKG HOWWORKS — Reference

Upstream (rendered): https://github.com/seregonwar/ShadPKG/blob/main/docs/HOWWORKS.md
Upstream (raw): https://raw.githubusercontent.com/seregonwar/ShadPKG/main/docs/HOWWORKS.md

Executive summary
- Deep, implementation-oriented walkthrough of PKG decryption → PFS key derivation → XTS/PFSC handling → extraction.
- Strongest single document for connecting PKG header/entry structures to actual decryption and filesystem access steps.

Highlights
- PKG header parsing; entry decryption using SHA256-derived IVs and AES-128-CBC; roles of dk0..dk6.
- EKPFS (dk1) to PFS key derivation via HMAC-SHA256(seed, index) keyed by EKPFS; XTS keys split from digest.
- PFSC logical block mapping; deflate path for compressed sectors; zero-fill branch for oversized sector mapping.
- Extraction loop from outer PKG → outer PFS (optional encryption) → inner PFSC-wrapped pfs_image.dat → inner PFS files.

Use this doc to
- Drive implementation parity: follow the sequence of keys, IVs, decryptions, and block mapping closely.
- Sanity-check assumptions against real samples or independent implementations (e.g., LibOrbisPkg).
