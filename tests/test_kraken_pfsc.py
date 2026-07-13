import struct

import mkpfs.kraken_pfsc as kf


def test_encode_decode_stored():
    raw = b"Hello PFSC!" * 500  # ~6000 bytes, smaller than default 256 KiB block
    container = kf.encode_pfsc_kraken_payload(raw)
    assert container[:4] == b"PFSC"
    version = struct.unpack_from("<H", container, 0x04)[0]
    assert version == 3
    block_size = struct.unpack_from("<I", container, 0x08)[0]
    assert block_size == 0x40000
    extracted = kf.decode_pfsc_kraken_payload(container)
    assert extracted == raw


def test_encode_decode_empty():
    raw = b""
    container = kf.encode_pfsc_kraken_payload(raw)
    assert container[:4] == b"PFSC"
    extracted = kf.decode_pfsc_kraken_payload(container)
    assert extracted == raw
