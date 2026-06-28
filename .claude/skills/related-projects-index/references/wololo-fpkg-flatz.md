# Wololo — PS4 FPKG writeup by flatz (Reference)

Upstream: https://wololo.net/ps4-fpkg-writeup-by-flatz/

Executive summary
- Deep, end‑to‑end account of enabling fake SELFs/PKGs on PS4: kernel hooks to accept FSELFs, toolchain key substitution to build FPKGs, ShellCore patches to install/run them, and kernel crypto shims to decrypt/verify PFS without Sony private keys.
- Defines EKPFS vs EEKPFS (escrowed EKPFS), shows how Orbis Publishing Tools’ sc.exe embeds an encrypted XML of keys, and documents replacing the RSA key used for mount‑image with a custom pair.
- Details PFS final key derivation (HMAC over seed+index, split into enc/sign) and how to bypass slot‑key usage by passing raw keys into CCP requests.

Why it matters (MkPFS scope)
- Clarifies production crypto boundaries around PFS in PKG (why unsigned PFSC/PFS flows are practical for homebrew and testing while retail keys remain out of scope).
- Provides authoritative names and data‑flow for EKPFS/EEKPFS, PFS seed, final enc/sign keys, and runtime mount behaviors — improving MkPFS docs and compatibility guidance.

Highlights and deep points
- FSELF loader path (kernel): hooks around sceSblAuthMgrIsLoadable2/VerifyHeader/LoadSelfSegment/LoadSelfBlock to accept unsigned content by substituting auth info and memcpy‑ing segments/blocks rather than SAMU decrypt.
- Toolchain edits:
  - sc.exe contains AES‑CBC encrypted XML whose IV/key equals SHA‑256 of plaintext XML; decrypt, edit mount‑image RSA modulus/exponents with custom key; re‑encrypt and splice back (size preserved).
  - orbis‑pub‑cmd.exe patch: treats arbitrary SELF like built‑in sce_sys/about/right.sprx to bypass “already converted to SELF” rejection.
  - Extract a debug/fake RIF key blob embedded in orbis‑pub‑cmd for kernel use.
- ShellCore patches: bypass genuine‑check routines to allow installing debug/fake packages; patch strings/branches to accept “free” rather than “fake” flow.
- Kernel PFS key path:
  - If SAMU EEKPFS→EKPFS fails for FPKG, decrypt EEKPFS with custom RSA (ypkg_* components) to recover EKPFS.
  - Derive PFS final keys via HMAC‑SHA256 over [index||seed]:
    - index=1 → encryption key; index=2 → signing key.
  - Detect fake keys (seed marker) and feed raw keys into CCP instead of slot keys; expose reader/writer shims to operate on PFSC blocks.

Notes / gotchas
- Offsets and hook sites differ by firmware; the writeup illustrates 4.05/4.55 examples.
- Custom RSA key components in kernel and sc.exe must match; byte order of big integers is significant in the code.
- Retail PKG/NPDRM pipelines remain asymmetric‑key protected; the writeup shows a parallel “fake” toolchain, not a derivation of Sony private keys.

Source index
- https://wololo.net/ps4-fpkg-writeup-by-flatz/
- Sections: Fake SELFs (kernel hooks), Fake PKGs (toolchain and ShellCore), Kernel code (EEKPFS→EKPFS, PFS final keys)