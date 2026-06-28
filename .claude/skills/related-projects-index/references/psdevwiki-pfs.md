# PSDevWiki — PFS page (Reference)

Upstream: https://www.psdevwiki.com/ps4/PFS

Executive summary
- Community reverse-engineering page focused on PFS on-disk structures and behavior.
- Strong for structure: superblock fields, block-size rules, inode/dirent layout, superroot/uroot, flat_path_table and collision handling.
- Complements implementation sources that cover crypto and operational flows.

Highlights
- PFS is described as UFS-like, with power-of-two block sizes and configurable profiles.
- Superroot contains uroot and synthetic files like flat_path_table (and collision resolver when needed).
- Dirents encode inode, type, name length, entry size; 8-byte alignment rules apply.
- Encryption is XTS-AES-128 in production images; seeds/keys are PKG-context dependent.

Use this page to
- Cross-check header fields and inode/dirent sizes.
- Confirm flat_path_table role and high-level hashing/collision notes before drilling into implementation code.
