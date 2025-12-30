#!/usr/bin/env python3
"""
Assassin's Creed Brotherhood - Compact Format Parser
=====================================================

Parser for SAV file Blocks 3 and 5 which use a compact binary format
with table-based type resolution and variable-length encoding.

Format Overview:
---------------
- 8-byte header (version, size, flags)
- Preamble region (initialization data)
- Data region with prefixed entries

Prefix Types:
-------------
| Prefix | Name       | Description                              |
|--------|------------|------------------------------------------|
| 0x0803 | TABLE_REF  | Table ID + Property Index reference      |
| 0x1405 | VARINT     | Variable-length integer                  |
| 0x0502 | FIXED32    | 32-bit fixed value                       |
| 0x1500 | VALUE_15   | 32-bit value (6 bytes total)             |
| 0x1200 | VALUE_12   | 32-bit value (6 bytes total)             |
| 0x1C04 | EXTENDED   | Extended value with type discriminator   |
| 0x173C | ARRAY_ELEM | Compact array/collection element         |
| 0x1006 | TYPE_REF   | Type reference                           |
| 0x1809 | PREFIX_18  | Extended marker                          |

Usage:
------
    python compact_format_parser.py references/sav_block3_raw.bin
    python compact_format_parser.py references/sav_block5_raw.bin --verbose
"""

import sys
import os
import struct
import argparse
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any, Union
from enum import Enum, auto


# =============================================================================
# Constants and Enums
# =============================================================================

class PrefixType(Enum):
    """Known compact format prefix types"""
    TABLE_REF = 0x0803      # Table ID + Property Index
    VARINT = 0x1405         # Variable-length integer
    FIXED32 = 0x0502        # 32-bit fixed value
    VALUE_15 = 0x1500       # 32-bit value (type 0x15)
    VALUE_12 = 0x1200       # 32-bit value (type 0x12)
    EXTENDED_1C = 0x1C04    # Extended value encoding
    ARRAY_ELEM = 0x173C     # Array element marker
    TYPE_REF_10 = 0x1006    # Type reference
    PREFIX_1809 = 0x1809    # Extended marker
    PREFIX_1907 = 0x1907    # Unknown prefix
    PREFIX_16E1 = 0x16E1    # Unknown prefix
    PREFIX_0C18 = 0x0C18    # Extended format
    UNKNOWN = 0x0000


# Table ID to Type Hash mapping (104 entries from table_id_hash_simple.json)
TABLE_ID_TO_TYPE = {
    0x00: (0x87BFB8DB, "CompactType_00"),
    0x01: (0x5B0885B7, "CompactType_01"),
    0x02: (0x95DE1A76, "CompactType_02"),
    0x03: (0x6EC3C146, "CompactType_03"),
    0x04: (0x1039317E, "CompactType_04"),
    0x05: (0x0B1CA4FF, "CompactType_05"),
    0x06: (0x08999B6B, "CompactType_06"),
    0x07: (0xE45C13C1, "CompactType_07"),
    0x08: (0xC9A5839D, "CompactType_08"),
    0x09: (0x723C7DFD, "CompactType_09"),
    0x0A: (0xC438CAAA, "CompactType_0A"),
    0x0B: (0x82A2AEE0, "CompactType_0B"),
    0x0C: (0x885FD270, "CompactType_0C"),
    0x0D: (0x9ED73EC7, "CompactType_0D"),
    0x0E: (0xB01D2FBC, "CompactType_0E"),
    0x0F: (0x635ED6FD, "CompactType_0F"),
    0x10: (0x21389788, "CompactType_10"),
    0x11: (0x7C0A22D2, "CompactType_11"),
    0x12: (0x5E9D4672, "CompactType_12"),
    0x13: (0x9464A1DF, "CompactType_13"),
    0x14: (0xCE77DEA9, "CompactType_14"),
    0x15: (0xF34AE634, "CompactType_15"),
    0x16: (0x0AFD89DC, "PlayerOptionsElement"),
    0x17: (0x6FEB4D3E, "CompactType_17"),
    0x18: (0x1BD6AF74, "CompactType_18"),
    0x19: (0x7EC06B96, "CompactType_19"),
    0x1A: (0xFE52CE42, "CompactType_1A"),
    0x1B: (0x1EAE1A27, "CompactType_1B"),
    0x1C: (0xEEFD3C62, "CompactType_1C"),
    0x1D: (0x8178B0FC, "CompactType_1D"),
    0x1E: (0x35A73BF9, "CompactType_1E"),
    0x1F: (0xD17B9E84, "CompactType_1F"),
    0x20: (0x1B2159BE, "CompactType_20"),
    0x21: (0xC30FCF3C, "CompactType_21"),
    0x22: (0xB2AC9ECF, "CompactType_22"),
    0x23: (0xEEA84BEB, "CompactType_23"),
    0x24: (0xA387B867, "CompactType_24"),
    0x25: (0x07F84685, "CompactType_25"),
    0x26: (0x04B26A6F, "CompactType_26"),
    0x27: (0x649B330F, "CompactType_27"),
    0x28: (0xB17CA151, "CompactType_28"),
    0x29: (0xFDDE216B, "CompactType_29"),
    0x2A: (0x2EF0DC94, "CompactType_2A"),
    0x2B: (0x0A0EF2AB, "CompactType_2B"),
    0x2C: (0x0DF38019, "CompactType_2C"),
    0x2D: (0xB3423CBF, "CompactType_2D"),
    0x2E: (0x79985A47, "CompactType_2E"),
    0x2F: (0xBE427635, "CompactType_2F"),
    0x30: (0x969057FD, "CompactType_30"),
    0x31: (0xC31A6D47, "CompactType_31"),
    0x32: (0x0DC752FA, "CompactType_32"),
    0x33: (0xF04DFE62, "CompactType_33"),
    0x34: (0xC38E48D7, "CompactType_34"),
    0x35: (0xEAAC8DA8, "CompactType_35"),
    0x36: (0x33D71609, "CompactType_36"),
    0x37: (0x5949EFD9, "CompactType_37"),
    0x38: (0xFA1AA549, "CompactType_38"),
    0x39: (0x8FC5A10C, "CompactType_39"),
    0x3A: (0x3C4C3BD2, "CompactType_3A"),
    0x3B: (0xFC6EDE2A, "CompactType_3B"),
    0x3C: (0xF5718FB1, "CompactType_3C"),
    0x3D: (0xE051FC8F, "CompactType_3D"),
    0x3E: (0x83BA68A2, "CompactType_3E"),
    0x3F: (0x6D2E5F10, "CompactType_3F"),
    0x40: (0x762B59C4, "CompactType_40"),
    0x41: (0x252E9992, "CompactType_41"),
    0x42: (0xB507DD42, "CompactType_42"),
    0x43: (0xE27BFE05, "CompactType_43"),
    0x44: (0x4DAC6313, "CompactType_44"),
    0x45: (0xAF9F222E, "CompactType_45"),
    0x46: (0xE4181084, "CompactType_46"),
    0x47: (0x289AD354, "CompactType_47"),
    0x48: (0x8D474522, "CompactType_48"),
    0x49: (0x144E1498, "CompactType_49"),
    0x4A: (0x6349240E, "CompactType_4A"),
    0x4B: (0xFD2DB1AD, "CompactType_4B"),
    0x4C: (0x8A2A813B, "CompactType_4C"),
    0x4D: (0x1323D081, "CompactType_4D"),
    0x4E: (0x6424E017, "CompactType_4E"),
    0x4F: (0xF49BFD86, "CompactType_4F"),
    0x50: (0x839CCD10, "CompactType_50"),
    0x51: (0xE35B44F5, "CompactType_51"),
    0x52: (0x945C7463, "CompactType_52"),
    0x53: (0x0D5525D9, "CompactType_53"),
    0x54: (0x7A52154F, "CompactType_54"),
    0x55: (0xE43680EC, "CompactType_55"),
    0x56: (0x9331B07A, "CompactType_56"),
    0x57: (0x0A38E1C0, "CompactType_57"),
    0x58: (0x7D3FD156, "CompactType_58"),
    0x59: (0xED80CCC7, "CompactType_59"),
    0x5A: (0x9A87FC51, "CompactType_5A"),
    0x5B: (0xC8761736, "CompactType_5B"),
    0x5C: (0xE3E58C35, "CompactType_5C"),
    0x5D: (0x7AECDD8F, "CompactType_5D"),
    0x5E: (0x0DEBED19, "CompactType_5E"),
    0x5F: (0x938F78BA, "CompactType_5F"),
    0x60: (0xE488482C, "CompactType_60"),
    0x61: (0xE2A997E4, "CompactType_61"),
    0x62: (0x7BA0C65E, "CompactType_62"),
    0x63: (0x0CA7F6C8, "CompactType_63"),
    0x64: (0x92C3636B, "CompactType_64"),
    0x65: (0xE5C453FD, "CompactType_65"),
    0x66: (0x06337DCC, "CompactType_66"),
    0x67: (0x78A90B6B, "CompactType_67"),
    # Additional table IDs found in save files (beyond the 104 verified entries)
    0x95: (0x00000000, "Unknown_95"),
    0xDB: (0x00000000, "Unknown_DB"),
    0xE1: (0x00000000, "Unknown_E1"),
    0xFB: (0x00000000, "Unknown_FB"),
}

# Marker byte meanings
MARKER_TRUE = 0x6D   # Boolean TRUE or value 1
MARKER_FALSE = 0xDB  # Boolean FALSE or value 0
MARKER_CD = 0xCD     # Unknown separator/flag


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class CompactHeader:
    """8-byte compact format header"""
    version: int        # 1 byte - always 0x01
    data_size: int      # 3 bytes - little-endian 24-bit
    flags: int          # 4 bytes - always 0x00800000
    raw_bytes: bytes    # Original 8 bytes

    @classmethod
    def parse(cls, data: bytes, offset: int = 0) -> 'CompactHeader':
        """Parse header from data at offset"""
        raw = data[offset:offset + 8]
        version = raw[0]
        data_size = raw[1] | (raw[2] << 8) | (raw[3] << 16)
        flags = struct.unpack('<I', raw[4:8])[0]
        return cls(version=version, data_size=data_size, flags=flags, raw_bytes=raw)


@dataclass
class TableRef:
    """TABLE_REF entry (0x0803 prefix)"""
    offset: int
    table_id: int
    property_id: int
    type_hash: Optional[int] = None
    type_name: Optional[str] = None

    def __post_init__(self):
        if self.table_id in TABLE_ID_TO_TYPE:
            self.type_hash, self.type_name = TABLE_ID_TO_TYPE[self.table_id]


@dataclass
class ExtendedValue:
    """Extended value entry (0x1C04 prefix)"""
    offset: int
    subtype: int
    value: Any
    raw_bytes: bytes


@dataclass
class ArrayElement:
    """Array element entry (0x173C prefix)"""
    offset: int
    element_type: int
    value: Any
    raw_bytes: bytes


@dataclass
class FixedValue:
    """Fixed 32-bit value (0x1500, 0x1200, 0x0502 prefixes)"""
    offset: int
    prefix: int
    value: int
    raw_bytes: bytes


@dataclass
class ParsedEntry:
    """Generic parsed entry wrapper"""
    offset: int
    prefix: int
    prefix_type: PrefixType
    data: Any
    size: int  # Total bytes consumed


@dataclass
class CompactBlock:
    """Fully parsed compact format block"""
    header: CompactHeader
    preamble: bytes
    entries: List[ParsedEntry]
    raw_data: bytes

    # Statistics
    table_refs: List[TableRef] = field(default_factory=list)
    extended_values: List[ExtendedValue] = field(default_factory=list)
    array_elements: List[ArrayElement] = field(default_factory=list)
    fixed_values: List[FixedValue] = field(default_factory=list)
    unknown_regions: List[Tuple[int, int, bytes]] = field(default_factory=list)


# =============================================================================
# Parser Class
# =============================================================================

class CompactFormatParser:
    """Parser for AC Brotherhood compact format blocks"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.stats = {
            'table_refs': 0,
            'extended_1c04': 0,
            'array_173c': 0,
            'value_1500': 0,
            'value_1200': 0,
            'fixed32_0502': 0,
            'varint_1405': 0,
            'type_ref_1006': 0,
            'prefix_1809': 0,
            'prefix_1907': 0,
            'prefix_1902': 0,
            'prefix_16e1': 0,
            'unknown': 0,
            'markers': {'0x6D': 0, '0xDB': 0, '0xCD': 0},
        }

    def parse(self, data: bytes) -> CompactBlock:
        """
        Parse a complete compact format block.

        Args:
            data: Raw block data (Block 3 or Block 5)

        Returns:
            CompactBlock with all parsed entries
        """
        # Parse header
        header = CompactHeader.parse(data, 0)

        if self.verbose:
            print(f"Header: version={header.version}, size={header.data_size}, flags=0x{header.flags:08X}")

        # Find first TABLE_REF to determine preamble end
        preamble_end = self._find_first_table_ref(data)
        preamble = data[8:preamble_end]

        if self.verbose:
            print(f"Preamble: {preamble_end - 8} bytes (0x08 to 0x{preamble_end:04X})")

        # Parse data region
        entries = []
        pos = preamble_end

        while pos < len(data) - 1:
            entry, consumed = self._parse_entry(data, pos)
            if entry:
                entries.append(entry)
                pos += consumed
            else:
                # Skip unknown byte
                pos += 1
                self.stats['unknown'] += 1

        # Build result
        block = CompactBlock(
            header=header,
            preamble=preamble,
            entries=entries,
            raw_data=data
        )

        # Categorize entries
        for entry in entries:
            if entry.prefix_type == PrefixType.TABLE_REF:
                block.table_refs.append(entry.data)
            elif entry.prefix_type == PrefixType.EXTENDED_1C:
                block.extended_values.append(entry.data)
            elif entry.prefix_type == PrefixType.ARRAY_ELEM:
                block.array_elements.append(entry.data)
            elif entry.prefix_type in (PrefixType.VALUE_15, PrefixType.VALUE_12, PrefixType.FIXED32):
                block.fixed_values.append(entry.data)

        return block

    def _find_first_table_ref(self, data: bytes) -> int:
        """Find offset of first TABLE_REF (0x0803) pattern"""
        for i in range(8, len(data) - 1):
            if data[i] == 0x08 and data[i+1] == 0x03:
                return i
        return 8  # Default to right after header

    def _parse_entry(self, data: bytes, pos: int) -> Tuple[Optional[ParsedEntry], int]:
        """
        Parse a single entry at the given position.

        Returns:
            Tuple of (ParsedEntry or None, bytes consumed)
        """
        if pos >= len(data) - 1:
            return None, 0

        # Read 2-byte prefix as big-endian (first byte is type indicator)
        b0 = data[pos]
        b1 = data[pos + 1]

        # TABLE_REF: 08 03 [table_id] [prop_id]
        if b0 == 0x08 and b1 == 0x03:
            return self._parse_table_ref(data, pos)

        # EXTENDED_1C: 1C 04 [subtype] [data...]
        if b0 == 0x1C and b1 == 0x04:
            return self._parse_extended_1c(data, pos)

        # ARRAY_ELEM: 17 3C [type] [data...]
        if b0 == 0x17 and b1 == 0x3C:
            return self._parse_array_element(data, pos)

        # VALUE_15: 15 00 [4-byte value]
        if b0 == 0x15 and b1 == 0x00:
            return self._parse_value_15(data, pos)

        # VALUE_12: 12 00 [4-byte value]
        if b0 == 0x12 and b1 == 0x00:
            return self._parse_value_12(data, pos)

        # FIXED32: 05 02 [4-byte value]
        if b0 == 0x05 and b1 == 0x02:
            return self._parse_fixed32(data, pos)

        # VARINT: 14 05 [varint...]
        if b0 == 0x14 and b1 == 0x05:
            return self._parse_varint(data, pos)

        # TYPE_REF: 10 06 [type ref...]
        if b0 == 0x10 and b1 == 0x06:
            return self._parse_type_ref(data, pos)

        # PREFIX_1809: 18 09 [data...]
        if b0 == 0x18 and b1 == 0x09:
            return self._parse_prefix_1809(data, pos)

        # PREFIX_1907: 19 07 [data...]
        if b0 == 0x19 and b1 == 0x07:
            return self._parse_prefix_1907(data, pos)

        # PREFIX_0C18: 0C 18 [data...]
        if b0 == 0x0C and b1 == 0x18:
            return self._parse_prefix_0c18(data, pos)

        # PREFIX_1013: 10 13 [data...]
        if b0 == 0x10 and b1 == 0x13:
            return self._parse_prefix_1013(data, pos)

        # PREFIX_1830: 18 30 [data...]
        if b0 == 0x18 and b1 == 0x30:
            return self._parse_prefix_1830(data, pos)

        # PREFIX_140E: 14 0E [data...]
        if b0 == 0x14 and b1 == 0x0E:
            return self._parse_prefix_140e(data, pos)

        # PREFIX_1902: 19 02 [data...] (frequent in Block 5)
        if b0 == 0x19 and b1 == 0x02:
            return self._parse_prefix_1902(data, pos)

        # PREFIX_16E1: 16 E1 [data...]
        if b0 == 0x16 and b1 == 0xE1:
            return self._parse_prefix_16e1(data, pos)

        # Check for single-byte markers
        b = data[pos]
        if b == MARKER_TRUE:
            self.stats['markers']['0x6D'] += 1
            return ParsedEntry(
                offset=pos, prefix=b, prefix_type=PrefixType.UNKNOWN,
                data={'marker': 'TRUE', 'value': 1}, size=1
            ), 1
        elif b == MARKER_FALSE:
            self.stats['markers']['0xDB'] += 1
            return ParsedEntry(
                offset=pos, prefix=b, prefix_type=PrefixType.UNKNOWN,
                data={'marker': 'FALSE', 'value': 0}, size=1
            ), 1
        elif b == MARKER_CD:
            self.stats['markers']['0xCD'] += 1
            return ParsedEntry(
                offset=pos, prefix=b, prefix_type=PrefixType.UNKNOWN,
                data={'marker': 'CD', 'value': None}, size=1
            ), 1

        return None, 1

    def _parse_table_ref(self, data: bytes, pos: int) -> Tuple[ParsedEntry, int]:
        """Parse TABLE_REF: 08 03 [table_id] [prop_id]"""
        if pos + 4 > len(data):
            return None, 0

        table_id = data[pos + 2]
        prop_id = data[pos + 3]

        ref = TableRef(offset=pos, table_id=table_id, property_id=prop_id)
        self.stats['table_refs'] += 1

        if self.verbose:
            type_info = f" ({ref.type_name})" if ref.type_name else ""
            print(f"  0x{pos:04X}: TABLE_REF table=0x{table_id:02X}{type_info}, prop=0x{prop_id:02X}")

        return ParsedEntry(
            offset=pos, prefix=0x0803, prefix_type=PrefixType.TABLE_REF,
            data=ref, size=4
        ), 4

    def _parse_extended_1c(self, data: bytes, pos: int) -> Tuple[ParsedEntry, int]:
        """Parse EXTENDED_1C: 1C 04 [subtype] [data...]"""
        if pos + 3 > len(data):
            return None, 0

        subtype = data[pos + 2]
        consumed = 3
        value = None

        # Decode based on subtype
        if subtype == 0x08:  # 1-byte value
            if pos + 4 <= len(data):
                value = data[pos + 3]
                consumed = 4
        elif subtype in (0x0A, 0x0B):  # 2-byte value
            if pos + 5 <= len(data):
                value = struct.unpack('<H', data[pos + 3:pos + 5])[0]
                consumed = 5
        elif subtype in (0x24, 0x25, 0x21, 0x23):  # Type/property reference (variable)
            # Read until we hit another prefix or marker
            end = pos + 3
            while end < len(data) and end < pos + 8:
                b = data[end]
                if b in (0x08, 0x1C, 0x17, 0x15, 0x12, 0x14, 0x10, 0x18, 0x19, 0x0C):
                    break
                if b in (MARKER_TRUE, MARKER_FALSE, MARKER_CD):
                    break
                end += 1
            value = data[pos + 3:end]
            consumed = end - pos
        else:
            # Unknown subtype - read 2 more bytes
            if pos + 5 <= len(data):
                value = struct.unpack('<H', data[pos + 3:pos + 5])[0]
                consumed = 5

        ext = ExtendedValue(
            offset=pos, subtype=subtype, value=value,
            raw_bytes=data[pos:pos + consumed]
        )
        self.stats['extended_1c04'] += 1

        if self.verbose:
            print(f"  0x{pos:04X}: EXTENDED_1C subtype=0x{subtype:02X}, value={value}")

        return ParsedEntry(
            offset=pos, prefix=0x1C04, prefix_type=PrefixType.EXTENDED_1C,
            data=ext, size=consumed
        ), consumed

    def _parse_array_element(self, data: bytes, pos: int) -> Tuple[ParsedEntry, int]:
        """Parse ARRAY_ELEM: 17 3C [type] [data...]"""
        if pos + 3 > len(data):
            return None, 0

        elem_type = data[pos + 2]
        consumed = 3
        value = None

        # Decode based on element type
        if elem_type == 0x00:  # Null/terminator
            if pos + 6 <= len(data):
                value = struct.unpack('<I', data[pos + 3:pos + 7])[0]
                consumed = 7
            else:
                consumed = 3
        elif elem_type == 0x08:  # 1-byte value
            if pos + 4 <= len(data):
                value = data[pos + 3]
                consumed = 4
        elif elem_type == 0x1A:  # Property reference
            if pos + 5 <= len(data):
                value = struct.unpack('<H', data[pos + 3:pos + 5])[0]
                consumed = 5
        elif elem_type in (0x0A, 0x0B, 0x0E):  # 2-byte values
            if pos + 5 <= len(data):
                value = struct.unpack('<H', data[pos + 3:pos + 5])[0]
                consumed = 5
        else:
            # Unknown - try 2-byte read
            if pos + 5 <= len(data):
                value = struct.unpack('<H', data[pos + 3:pos + 5])[0]
                consumed = 5

        elem = ArrayElement(
            offset=pos, element_type=elem_type, value=value,
            raw_bytes=data[pos:pos + consumed]
        )
        self.stats['array_173c'] += 1

        if self.verbose:
            print(f"  0x{pos:04X}: ARRAY_ELEM type=0x{elem_type:02X}, value={value}")

        return ParsedEntry(
            offset=pos, prefix=0x173C, prefix_type=PrefixType.ARRAY_ELEM,
            data=elem, size=consumed
        ), consumed

    def _parse_value_15(self, data: bytes, pos: int) -> Tuple[ParsedEntry, int]:
        """Parse VALUE_15: 15 00 [4-byte value]"""
        if pos + 6 > len(data):
            return None, 0

        value = struct.unpack('<I', data[pos + 2:pos + 6])[0]

        fv = FixedValue(
            offset=pos, prefix=0x1500, value=value,
            raw_bytes=data[pos:pos + 6]
        )
        self.stats['value_1500'] += 1

        if self.verbose:
            print(f"  0x{pos:04X}: VALUE_15 = 0x{value:08X}")

        return ParsedEntry(
            offset=pos, prefix=0x1500, prefix_type=PrefixType.VALUE_15,
            data=fv, size=6
        ), 6

    def _parse_value_12(self, data: bytes, pos: int) -> Tuple[ParsedEntry, int]:
        """Parse VALUE_12: 12 00 [4-byte value]"""
        if pos + 6 > len(data):
            return None, 0

        value = struct.unpack('<I', data[pos + 2:pos + 6])[0]

        fv = FixedValue(
            offset=pos, prefix=0x1200, value=value,
            raw_bytes=data[pos:pos + 6]
        )
        self.stats['value_1200'] += 1

        if self.verbose:
            print(f"  0x{pos:04X}: VALUE_12 = 0x{value:08X}")

        return ParsedEntry(
            offset=pos, prefix=0x1200, prefix_type=PrefixType.VALUE_12,
            data=fv, size=6
        ), 6

    def _parse_fixed32(self, data: bytes, pos: int) -> Tuple[ParsedEntry, int]:
        """Parse FIXED32: 05 02 [4-byte value]"""
        if pos + 6 > len(data):
            return None, 0

        value = struct.unpack('<I', data[pos + 2:pos + 6])[0]

        fv = FixedValue(
            offset=pos, prefix=0x0502, value=value,
            raw_bytes=data[pos:pos + 6]
        )
        self.stats['fixed32_0502'] += 1

        if self.verbose:
            print(f"  0x{pos:04X}: FIXED32 = 0x{value:08X}")

        return ParsedEntry(
            offset=pos, prefix=0x0502, prefix_type=PrefixType.FIXED32,
            data=fv, size=6
        ), 6

    def _parse_varint(self, data: bytes, pos: int) -> Tuple[ParsedEntry, int]:
        """Parse VARINT: 14 05 [varint...]"""
        if pos + 3 > len(data):
            return None, 0

        # Read varint starting at pos+2
        value, varint_len = self._read_varint(data, pos + 2)
        consumed = 2 + varint_len

        self.stats['varint_1405'] += 1

        if self.verbose:
            print(f"  0x{pos:04X}: VARINT = {value}")

        return ParsedEntry(
            offset=pos, prefix=0x1405, prefix_type=PrefixType.VARINT,
            data={'value': value, 'raw': data[pos:pos + consumed]}, size=consumed
        ), consumed

    def _parse_type_ref(self, data: bytes, pos: int) -> Tuple[ParsedEntry, int]:
        """Parse TYPE_REF: 10 06 [table_id] [data...]"""
        if pos + 4 > len(data):
            return None, 0

        table_id = data[pos + 2]
        extra = data[pos + 3] if pos + 3 < len(data) else 0

        self.stats['type_ref_1006'] += 1

        if self.verbose:
            print(f"  0x{pos:04X}: TYPE_REF table=0x{table_id:02X}, extra=0x{extra:02X}")

        return ParsedEntry(
            offset=pos, prefix=0x1006, prefix_type=PrefixType.TYPE_REF_10,
            data={'table_id': table_id, 'extra': extra}, size=4
        ), 4

    def _parse_prefix_1809(self, data: bytes, pos: int) -> Tuple[ParsedEntry, int]:
        """Parse PREFIX_1809: 18 09 [data...]"""
        if pos + 4 > len(data):
            return None, 0

        value = struct.unpack('<H', data[pos + 2:pos + 4])[0]

        self.stats['prefix_1809'] += 1

        if self.verbose:
            print(f"  0x{pos:04X}: PREFIX_1809 = 0x{value:04X}")

        return ParsedEntry(
            offset=pos, prefix=0x1809, prefix_type=PrefixType.PREFIX_1809,
            data={'value': value}, size=4
        ), 4

    def _parse_prefix_1907(self, data: bytes, pos: int) -> Tuple[ParsedEntry, int]:
        """Parse PREFIX_1907: 19 07 [data...]"""
        if pos + 4 > len(data):
            return None, 0

        value = struct.unpack('<H', data[pos + 2:pos + 4])[0]

        self.stats['prefix_1907'] += 1

        if self.verbose:
            print(f"  0x{pos:04X}: PREFIX_1907 = 0x{value:04X}")

        return ParsedEntry(
            offset=pos, prefix=0x1907, prefix_type=PrefixType.PREFIX_1907,
            data={'value': value}, size=4
        ), 4

    def _parse_prefix_0c18(self, data: bytes, pos: int) -> Tuple[ParsedEntry, int]:
        """Parse PREFIX_0C18: 0C 18 [data...]"""
        if pos + 4 > len(data):
            return None, 0

        value = struct.unpack('<H', data[pos + 2:pos + 4])[0]

        if self.verbose:
            print(f"  0x{pos:04X}: PREFIX_0C18 = 0x{value:04X}")

        return ParsedEntry(
            offset=pos, prefix=0x0C18, prefix_type=PrefixType.PREFIX_0C18,
            data={'value': value}, size=4
        ), 4

    def _parse_prefix_1013(self, data: bytes, pos: int) -> Tuple[ParsedEntry, int]:
        """Parse PREFIX_1013: 10 13 [data...]"""
        if pos + 4 > len(data):
            return None, 0

        value = struct.unpack('<H', data[pos + 2:pos + 4])[0]

        if self.verbose:
            print(f"  0x{pos:04X}: PREFIX_1013 = 0x{value:04X}")

        return ParsedEntry(
            offset=pos, prefix=0x1013, prefix_type=PrefixType.UNKNOWN,
            data={'value': value}, size=4
        ), 4

    def _parse_prefix_1830(self, data: bytes, pos: int) -> Tuple[ParsedEntry, int]:
        """Parse PREFIX_1830: 18 30 [data...]"""
        if pos + 4 > len(data):
            return None, 0

        value = struct.unpack('<H', data[pos + 2:pos + 4])[0]

        if self.verbose:
            print(f"  0x{pos:04X}: PREFIX_1830 = 0x{value:04X}")

        return ParsedEntry(
            offset=pos, prefix=0x1830, prefix_type=PrefixType.UNKNOWN,
            data={'value': value}, size=4
        ), 4

    def _parse_prefix_140e(self, data: bytes, pos: int) -> Tuple[ParsedEntry, int]:
        """Parse PREFIX_140E: 14 0E [data...]"""
        if pos + 4 > len(data):
            return None, 0

        value = struct.unpack('<H', data[pos + 2:pos + 4])[0]

        if self.verbose:
            print(f"  0x{pos:04X}: PREFIX_140E = 0x{value:04X}")

        return ParsedEntry(
            offset=pos, prefix=0x140E, prefix_type=PrefixType.UNKNOWN,
            data={'value': value}, size=4
        ), 4

    def _parse_prefix_1902(self, data: bytes, pos: int) -> Tuple[ParsedEntry, int]:
        """Parse PREFIX_1902: 19 02 [data...]"""
        if pos + 4 > len(data):
            return None, 0

        value = struct.unpack('<H', data[pos + 2:pos + 4])[0]

        if self.verbose:
            print(f"  0x{pos:04X}: PREFIX_1902 = 0x{value:04X}")

        self.stats['prefix_1902'] += 1

        return ParsedEntry(
            offset=pos, prefix=0x1902, prefix_type=PrefixType.UNKNOWN,
            data={'value': value}, size=4
        ), 4

    def _parse_prefix_16e1(self, data: bytes, pos: int) -> Tuple[ParsedEntry, int]:
        """Parse PREFIX_16E1: 16 E1 [data...]"""
        if pos + 4 > len(data):
            return None, 0

        value = struct.unpack('<H', data[pos + 2:pos + 4])[0]

        if self.verbose:
            print(f"  0x{pos:04X}: PREFIX_16E1 = 0x{value:04X}")

        self.stats['prefix_16e1'] += 1

        return ParsedEntry(
            offset=pos, prefix=0x16E1, prefix_type=PrefixType.UNKNOWN,
            data={'value': value}, size=4
        ), 4

    def _read_varint(self, data: bytes, pos: int) -> Tuple[int, int]:
        """
        Read a variable-length integer (protobuf-style).

        Returns:
            Tuple of (value, bytes consumed)
        """
        result = 0
        shift = 0
        consumed = 0

        while pos + consumed < len(data):
            b = data[pos + consumed]
            result |= (b & 0x7F) << shift
            consumed += 1
            if (b & 0x80) == 0:
                break
            shift += 7
            if consumed > 5:  # Max 5 bytes for 32-bit varint
                break

        return result, consumed

    def print_stats(self):
        """Print parsing statistics"""
        print("\n" + "=" * 60)
        print("PARSING STATISTICS")
        print("=" * 60)
        print(f"  TABLE_REF (0x0803):     {self.stats['table_refs']:4d}")
        print(f"  EXTENDED_1C (0x1C04):   {self.stats['extended_1c04']:4d}")
        print(f"  ARRAY_ELEM (0x173C):    {self.stats['array_173c']:4d}")
        print(f"  VALUE_15 (0x1500):      {self.stats['value_1500']:4d}")
        print(f"  VALUE_12 (0x1200):      {self.stats['value_1200']:4d}")
        print(f"  FIXED32 (0x0502):       {self.stats['fixed32_0502']:4d}")
        print(f"  VARINT (0x1405):        {self.stats['varint_1405']:4d}")
        print(f"  TYPE_REF (0x1006):      {self.stats['type_ref_1006']:4d}")
        print(f"  PREFIX_1809:            {self.stats['prefix_1809']:4d}")
        print(f"  PREFIX_1907:            {self.stats['prefix_1907']:4d}")
        print(f"  PREFIX_1902:            {self.stats['prefix_1902']:4d}")
        print(f"  PREFIX_16E1:            {self.stats['prefix_16e1']:4d}")
        print(f"  Unknown bytes:          {self.stats['unknown']:4d}")
        print()
        print("  Markers:")
        for marker, count in self.stats['markers'].items():
            print(f"    {marker}: {count:4d}")
        print("=" * 60)


# =============================================================================
# Analysis Functions
# =============================================================================

def analyze_table_refs(block: CompactBlock):
    """Analyze TABLE_REF distribution"""
    print("\n" + "=" * 60)
    print("TABLE_REF ANALYSIS")
    print("=" * 60)

    # Group by table ID
    by_table = {}
    for ref in block.table_refs:
        if ref.table_id not in by_table:
            by_table[ref.table_id] = []
        by_table[ref.table_id].append(ref)

    print(f"\nTotal TABLE_REFs: {len(block.table_refs)}")
    print(f"Unique tables: {len(by_table)}")
    print()

    for table_id in sorted(by_table.keys()):
        refs = by_table[table_id]
        props = sorted(set(r.property_id for r in refs))
        type_name = refs[0].type_name or "Unknown"

        print(f"Table 0x{table_id:02X} ({type_name}): {len(refs)} refs")
        print(f"  Properties: {', '.join(f'0x{p:02X}' for p in props[:10])}", end='')
        if len(props) > 10:
            print(f" ... ({len(props)} total)")
        else:
            print()


def analyze_extended_values(block: CompactBlock):
    """Analyze EXTENDED_1C value distribution"""
    print("\n" + "=" * 60)
    print("EXTENDED_1C (0x1C04) ANALYSIS")
    print("=" * 60)

    # Group by subtype
    by_subtype = {}
    for ext in block.extended_values:
        if ext.subtype not in by_subtype:
            by_subtype[ext.subtype] = []
        by_subtype[ext.subtype].append(ext)

    print(f"\nTotal EXTENDED_1C values: {len(block.extended_values)}")
    print(f"Unique subtypes: {len(by_subtype)}")
    print()

    for subtype in sorted(by_subtype.keys()):
        values = by_subtype[subtype]
        print(f"Subtype 0x{subtype:02X}: {len(values)} occurrences")

        # Show sample values
        sample = values[:3]
        for v in sample:
            print(f"    0x{v.offset:04X}: value={v.value}")


def analyze_array_elements(block: CompactBlock):
    """Analyze ARRAY_ELEM distribution"""
    print("\n" + "=" * 60)
    print("ARRAY_ELEM (0x173C) ANALYSIS")
    print("=" * 60)

    if not block.array_elements:
        print("\nNo array elements found")
        return

    # Group by offset clusters
    elements = sorted(block.array_elements, key=lambda e: e.offset)

    print(f"\nTotal array elements: {len(block.array_elements)}")

    # Find clusters (elements within 100 bytes of each other)
    clusters = []
    current_cluster = [elements[0]]

    for i in range(1, len(elements)):
        if elements[i].offset - current_cluster[-1].offset < 100:
            current_cluster.append(elements[i])
        else:
            clusters.append(current_cluster)
            current_cluster = [elements[i]]
    clusters.append(current_cluster)

    print(f"Clusters found: {len(clusters)}")

    for i, cluster in enumerate(clusters):
        start = cluster[0].offset
        end = cluster[-1].offset
        print(f"\n  Cluster {i+1}: offset 0x{start:04X} - 0x{end:04X} ({len(cluster)} elements)")

        # Group by type
        by_type = {}
        for elem in cluster:
            if elem.element_type not in by_type:
                by_type[elem.element_type] = []
            by_type[elem.element_type].append(elem)

        for elem_type in sorted(by_type.keys()):
            elems = by_type[elem_type]
            print(f"    Type 0x{elem_type:02X}: {len(elems)} elements")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='AC Brotherhood Compact Format Parser',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python compact_format_parser.py references/sav_block3_raw.bin
  python compact_format_parser.py references/sav_block5_raw.bin --verbose
  python compact_format_parser.py references/sav_block3_raw.bin --analyze
"""
    )

    parser.add_argument('input', help='Input block file (Block 3 or Block 5)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Print each parsed entry')
    parser.add_argument('--analyze', '-a', action='store_true',
                        help='Show detailed analysis of parsed data')
    parser.add_argument('--output', '-o', type=str,
                        help='Output JSON file for parsed data')

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: File not found: {args.input}")
        return 1

    with open(args.input, 'rb') as f:
        data = f.read()

    print("=" * 60)
    print("AC Brotherhood Compact Format Parser")
    print("=" * 60)
    print(f"\nInput: {args.input}")
    print(f"Size: {len(data):,} bytes")

    # Parse
    parser_obj = CompactFormatParser(verbose=args.verbose)
    block = parser_obj.parse(data)

    # Print header info
    print(f"\nHeader:")
    print(f"  Version: {block.header.version}")
    print(f"  Data size: {block.header.data_size}")
    print(f"  Flags: 0x{block.header.flags:08X}")
    print(f"\nPreamble size: {len(block.preamble)} bytes")
    print(f"Entries parsed: {len(block.entries)}")

    # Print stats
    parser_obj.print_stats()

    # Detailed analysis
    if args.analyze:
        analyze_table_refs(block)
        analyze_extended_values(block)
        analyze_array_elements(block)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  TABLE_REFs:       {len(block.table_refs)}")
    print(f"  Extended values:  {len(block.extended_values)}")
    print(f"  Array elements:   {len(block.array_elements)}")
    print(f"  Fixed values:     {len(block.fixed_values)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
