#!/usr/bin/env python3
"""
Cape Unlocker for AC Brotherhood SAV files
==========================================

Unlocks the two Facebook-exclusive capes by flipping ownership flags in Block 4.

Offsets (in decompressed Block 4):
  0x50E0: Cape 1 flag (00 -> 01)
  0x50F2: Cape 2 flag (00 -> 01)
"""

import sys
import os
import struct
import argparse

# Import from existing tools
from lzss_decompressor_final import LZSSDecompressor
from lzss_compressor_final import compress_lzss_lazy
from sav_serializer import build_block1_header, build_block2_header, adler32

# Cape flag offsets in decompressed Block 4
CAPE1_OFFSET = 0x50E0
CAPE2_OFFSET = 0x50F2


def parse_sav_blocks(data: bytes) -> dict:
    """
    Parse SAV file and extract all 5 blocks.

    Block 3 has 4 regions with header pattern: [01] [size 3B] [00 00 80 00]
    Region 4's declared size equals Block 4's compressed size.
    """
    total_size = len(data)

    # Block 1: 44-byte header at offset 0, then compressed data
    block1_compressed_size = struct.unpack('<I', data[0x20:0x24])[0]
    block1_compressed = data[0x2C:0x2C + block1_compressed_size]

    # Block 2: 44-byte header immediately after Block 1
    block2_header_offset = 0x2C + block1_compressed_size
    block2_compressed_size = struct.unpack('<I', data[block2_header_offset + 0x20:block2_header_offset + 0x24])[0]
    block2_data_offset = block2_header_offset + 44
    block2_compressed = data[block2_data_offset:block2_data_offset + block2_compressed_size]

    # Block 3: Raw data with 4 regions
    block3_offset = block2_data_offset + block2_compressed_size

    # Find all 4 region headers in Block 3
    block3_regions = []
    search_pos = block3_offset
    for region_num in range(4):
        while search_pos < total_size - 8:
            if (data[search_pos] == 0x01 and
                data[search_pos+4:search_pos+8] == b'\x00\x00\x80\x00'):
                region_size = struct.unpack('<I', data[search_pos+1:search_pos+4] + b'\x00')[0]
                if 0 < region_size < 50000:
                    block3_regions.append((search_pos, region_size))
                    # Move past header + data + 5-byte gap
                    search_pos = search_pos + 8 + region_size + 5
                    break
            search_pos += 1

    # Region 4's declared size equals Block 4's compressed size
    if len(block3_regions) >= 4:
        region4_offset, block4_compressed_size = block3_regions[3]
        # Block 3 ends after Region 4 header (8 bytes) + 5-byte local data
        block3_end = region4_offset + 8 + 5
        block3_size = block3_end - block3_offset
    else:
        raise ValueError(f"Could not parse Block 3 headers, found {len(block3_regions)} regions")

    block3_raw = data[block3_offset:block3_offset + block3_size]

    # Calculate Region 4's offset within Block 3 (for later patching)
    region4_offset_in_block3 = region4_offset - block3_offset

    # Block 4: LZSS compressed, size from Region 4's declared value
    block4_offset = block3_offset + block3_size
    block4_compressed = data[block4_offset:block4_offset + block4_compressed_size]

    # Block 5: Rest of file
    block5_offset = block4_offset + block4_compressed_size
    block5_raw = data[block5_offset:]

    return {
        'block1_compressed': block1_compressed,
        'block2_compressed': block2_compressed,
        'block3_raw': block3_raw,
        'block4_compressed': block4_compressed,
        'block5_raw': block5_raw,
        'region4_offset_in_block3': region4_offset_in_block3,
    }


def unlock_capes(sav_path: str, output_path: str, verbose: bool = False) -> bool:
    """
    Unlock Facebook capes in a SAV file.
    """
    # Read input file
    with open(sav_path, 'rb') as f:
        sav_data = f.read()

    if verbose:
        print(f"Input: {sav_path} ({len(sav_data)} bytes)")

    # Parse SAV structure
    blocks = parse_sav_blocks(sav_data)

    block1_compressed = blocks['block1_compressed']
    block2_compressed = blocks['block2_compressed']
    block3_raw = bytearray(blocks['block3_raw'])  # Make mutable for patching
    block4_compressed = blocks['block4_compressed']
    block5_raw = blocks['block5_raw']
    region4_offset = blocks['region4_offset_in_block3']

    if verbose:
        print(f"Block 1 compressed: {len(block1_compressed)} bytes")
        print(f"Block 2 compressed: {len(block2_compressed)} bytes")
        print(f"Block 3 raw: {len(block3_raw)} bytes")
        print(f"Block 4 compressed: {len(block4_compressed)} bytes")
        print(f"Block 5 raw: {len(block5_raw)} bytes")

    # Decompress blocks
    decompressor = LZSSDecompressor()
    block1_decompressed = decompressor.decompress(block1_compressed)
    block2_decompressed = decompressor.decompress(block2_compressed)
    block4_decompressed = decompressor.decompress(block4_compressed)

    if verbose:
        print(f"Block 4 decompressed: {len(block4_decompressed)} bytes")

    # Check current cape status
    block4_data = bytearray(block4_decompressed)
    cape1_current = block4_data[CAPE1_OFFSET]
    cape2_current = block4_data[CAPE2_OFFSET]

    print(f"Cape 1 (0x{CAPE1_OFFSET:04X}): {cape1_current:02X} -> 01")
    print(f"Cape 2 (0x{CAPE2_OFFSET:04X}): {cape2_current:02X} -> 01")

    if cape1_current == 0x01 and cape2_current == 0x01:
        print("Both capes already unlocked!")
        return True

    # Flip the flags
    block4_data[CAPE1_OFFSET] = 0x01
    block4_data[CAPE2_OFFSET] = 0x01

    # Recompress blocks
    if verbose:
        print("Recompressing blocks...")
    block1_recompressed, _, _ = compress_lzss_lazy(block1_decompressed)
    block2_recompressed, _, _ = compress_lzss_lazy(block2_decompressed)
    block4_recompressed, _, _ = compress_lzss_lazy(bytes(block4_data))

    if verbose:
        print(f"Block 4 recompressed: {len(block4_recompressed)} bytes")

    # Patch Block 3's Region 4 header with new Block 4 size
    # Region 4 format: [01] [size 3B LE] [00 00 80 00] [00] [checksum 4B LE]
    # Size is at offset +1 (3 bytes), checksum is at offset +9 (4 bytes)
    old_size = struct.unpack('<I', bytes(block3_raw[region4_offset+1:region4_offset+4]) + b'\x00')[0]
    new_size = len(block4_recompressed)
    if old_size != new_size:
        if verbose:
            print(f"Patching Block 3 Region 4 size: {old_size} -> {new_size}")
        # Write new size as 24-bit little-endian
        size_bytes = struct.pack('<I', new_size)[:3]
        block3_raw[region4_offset+1:region4_offset+4] = size_bytes

    # Update the Adler32 checksum of Block 4 LZSS data in the 5-byte prefix
    # Prefix is at region4_offset+8: [00] [checksum 4B LE]
    old_checksum = struct.unpack('<I', bytes(block3_raw[region4_offset+9:region4_offset+13]))[0]
    new_checksum = adler32(block4_recompressed)
    if old_checksum != new_checksum:
        if verbose:
            print(f"Patching Block 4 checksum: 0x{old_checksum:08X} -> 0x{new_checksum:08X}")
        block3_raw[region4_offset+9:region4_offset+13] = struct.pack('<I', new_checksum)

    # Calculate remaining file size for Block 2 header
    remaining_after_block2_header = (
        44 + len(block2_recompressed) +
        len(block3_raw) +
        len(block4_recompressed) +
        len(block5_raw)
    )

    # Build headers
    block1_header = build_block1_header(block1_recompressed, len(block1_decompressed))
    block2_header = build_block2_header(block2_recompressed, len(block2_decompressed),
                                        remaining_after_block2_header)

    # Assemble output file
    output = bytearray()
    output.extend(block1_header)
    output.extend(block1_recompressed)
    output.extend(block2_header)
    output.extend(block2_recompressed)
    output.extend(block3_raw)
    output.extend(block4_recompressed)
    output.extend(block5_raw)

    # Write output
    with open(output_path, 'wb') as f:
        f.write(output)

    print(f"Output: {output_path} ({len(output)} bytes)")
    print("Capes unlocked!")

    return True


def main():
    parser = argparse.ArgumentParser(description='Unlock Facebook capes in AC Brotherhood SAV files')
    parser.add_argument('input', help='Input SAV file')
    parser.add_argument('-o', '--output', help='Output SAV file (default: input with .unlocked.SAV)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"ERROR: File not found: {args.input}")
        return 1

    # Default output name
    if args.output is None:
        base, ext = os.path.splitext(args.input)
        args.output = f"{base}.unlocked{ext}"

    try:
        unlock_capes(args.input, args.output, args.verbose)
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
