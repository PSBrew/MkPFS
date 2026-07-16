import zlib
from typing import Any

import mkpfs.kraken_pfsc as kf
import mkpfs.oodle as oodle


def test_encode_decode_compressed(monkeypatch: Any) -> None:
    # Create a predictable compressible payload of 2 * 128KiB = 256KiB
    CHUNK_SIZE = 0x20000
    payload = b"A" * (CHUNK_SIZE * 2)

    def zlib_encode(block_bytes: bytes, level: int) -> bytes:
        # Use zlib to produce smaller-than-threshold compressed chunks
        return zlib.compress(block_bytes, level=9)

    def fake_decompress(comp_block: bytes, expected_size: int) -> bytes:
        # Decompress concatenated zlib streams
        out = bytearray()
        buf = comp_block
        while buf:
            d = zlib.decompressobj()
            chunk = d.decompress(buf)
            out.extend(chunk)
            # unused_data holds the bytes after the first compressed stream
            if d.unused_data:
                buf = d.unused_data
            else:
                break
        if len(out) != expected_size:
            raise RuntimeError(f"decompressed size mismatch: got {len(out)}, expected {expected_size}")
        return bytes(out)

    # Monkeypatch the Oodle decompressor to our zlib-based fake for the test
    monkeypatch.setattr(oodle, "decompress_kraken_block", fake_decompress, raising=False)

    container = kf.encode_pfsc_kraken_payload(payload, encode_block_fn=zlib_encode)
    extracted = kf.decode_pfsc_kraken_payload(container)
    assert extracted == payload
