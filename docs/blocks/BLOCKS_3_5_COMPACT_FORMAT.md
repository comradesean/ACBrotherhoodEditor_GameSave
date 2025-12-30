# SAV Blocks 3 and 5 Compact Format Specification

> **Investigation Status: PAUSED** (December 30, 2024)
>
> The nibble extraction code for table IDs has not been located. We traced deep into
> the PropertyData handler chain but found only raw byte readers. The compact format
> parsing path appears separate from the TYPE_REF dispatcher (which uses 4-byte hashes).
> See HANDOFF_SAV_DESERIALIZERS.md for detailed session notes and next steps.

## Overview

Blocks 3 and 5 in AC Brotherhood SAV files use a compact binary format for serializing game object properties. Unlike Blocks 2 and 4 which use LZSS compression with raw type hashes, these blocks use table ID lookup for type resolution, resulting in more compact property references.

### Deserializer

**Updated Finding (December 2024):** Blocks 3 and 5 are NOT processed through the main block deserializer vtable dispatch. Instead, they are processed as **PropertyData** through `FUN_01b11a50`.

The PropertyData handler checks the version byte at the start of the data:
- Version `0x01`: Routes to `FUN_01b702e0` or `FUN_01b70450`
- Version `0x02`: Routes to `FUN_01b70380` or `FUN_01b704f0`
- Version `0x03`: Routes to `FUN_01b71200` or `FUN_01b709a0`

Since Blocks 3 and 5 start with version byte `0x01`, they are handled by the Version 1 handlers.

**Previous Understanding (Partially Incorrect):**
- The Raw deserializer (`FUN_01712660`) was previously thought to handle these blocks
- TTD tracing confirmed this is NOT the entry point for Blocks 3/5

**Note:** The magic values `0x11FACE11` and `0x21EFFE22` are OPTIONS file section markers, not SAV block format identifiers. SAV blocks use different content formats (see below).

### Table ID Lookup System

The compact format uses table IDs to reference types. The lookup is performed by `FUN_01AEAF70`:

**Call chain:** `FUN_01AEAF70` -> `FUN_01AEAD60` -> `FUN_01AEA0B0`

**Table ID Encoding** (from `type_descriptor[+4]`):
```c
raw_value = type_desc[+4] & 0xC3FFFFFF;
table_id = raw_value - 1;
bucket_index = table_id >> 14;       // Upper bits = bucket
entry_index = table_id & 0x3FFF;     // Lower 14 bits = entry (max 16383)
address = table[bucket * 12] + entry * 16;
```

**Table structure** (at `[manager + 0x98]`):
- Count at `[manager + 0x9E]` (masked with 0x3FFF)
- Each bucket: 12 bytes (3 dwords)
- Each entry: 16 bytes (4 dwords)

## Block Characteristics

| Property | Block 3 | Block 5 |
|----------|---------|---------|
| Compression | Uncompressed | Uncompressed |
| Size | 7,972 bytes | 6,266 bytes |
| First TABLE_REF offset | 0x004E | 0x0113 |
| Preamble size | 70 bytes | 267 bytes |
| TABLE_REF count | 80 | 10 |
| Primary table | 0x5E (63 refs) | Distributed |

## Block Header (8 bytes)

Both blocks share the same header structure:

```
Offset  Size  Description
0x00    1     Version (always 0x01)
0x01    3     Data size (little-endian 24-bit)
0x04    4     Flags (always 0x00800000)
```

### Header Examples

```
Block 3: 01 39 0E 00 00 00 80 00
         |  |        |
         |  |        +- Flags: 0x00800000
         |  +---------- Size: 0x0E39 (3641)
         +------------- Version: 0x01

Block 5: 01 57 07 00 00 00 80 00
         |  |        |
         |  |        +- Flags: 0x00800000
         |  +---------- Size: 0x0757 (1879)
         +------------- Version: 0x01
```

Note: The size field does not directly correspond to block size. Its exact meaning is unclear but may indicate payload size or entry count.

## Preamble Region

Following the 8-byte header, each block has a preamble region that extends until the first TABLE_REF (0x0803) pattern. The preamble contains:

- Object descriptors
- Type references (including PropertyReference 0x0984415E)
- Initial value definitions

### Block 3 Preamble (70 bytes, 0x08-0x4E)

```
0008: 00 3d 64 0f e1 20 22 6c 9f 0e 00 c0 00 b6 6c a5
0018: 72 00 a1 00 24 0b 01 11 cd de 4c 09 b8 f2 00 00
0028: 11 c1 05 e3 a9 bf ce 90 00 6a 07 11 01 00 08 0b
0038: 50 79 1e 32 56 07 2a 4e 03 61 2e 41 6f 6a 5b ef
0048: 01 87 d8 ad b1 60
```

### Block 5 Preamble (267 bytes, 0x08-0x113)

Contains PropertyReference hash (0x0984415E) at offset 0x002D, along with multiple VARINT_1405 and VALUE prefixes.

## Compact Format Prefixes

The data region uses 2-byte prefixes to indicate data types:

### Primary Prefixes

| Prefix | Name | Description | Block 3 Count | Block 5 Count |
|--------|------|-------------|---------------|---------------|
| 0x0803 | TABLE_REF | Table ID + Property Index reference | 80 | 10 |
| 0x1405 | VARINT | Variable-length integer prefix | 83 | 58 |
| 0x0502 | FIXED32 | 32-bit fixed value | 75 | 66 |
| 0x1500 | VALUE_15 | 32-bit value (6 bytes total) | 44 | 11 |
| 0x1200 | VALUE_12 | 32-bit value (6 bytes total) | 47 | 34 |

### Secondary Prefixes

| Prefix | Name | Block 3 Count | Block 5 Count |
|--------|------|---------------|---------------|
| 0x1C04 | PREFIX_1C04 | 62 | 1 |
| 0x173C | PREFIX_173C | 32 | 32 |
| 0x1907 | PREFIX_1907 | 31 | 34 |
| 0x16E1 | PREFIX_16E1 | 22 | 21 |
| 0x1809 | PREFIX_1809 | 19 | 0 |
| 0x0C18 | EXTENDED | 14 | 1 |
| 0x1006 | PREFIX_1006 | 11 | 2 |

#### PREFIX_1C04 Sub-Type Distribution (Block 3)

The byte following PREFIX_1C04 acts as a sub-type discriminator:

| Sub-Type | Count | Purpose (Hypothesis) |
|----------|-------|----------------------|
| 0x0B (11) | 23 | Small signed/unsigned integers (most common) |
| 0x0A (10) | 15 | Small signed/unsigned integers |
| 0x25 (37) | 10 | Type reference or property ID |
| 0x08 (8) | 5 | Boolean or byte values |
| 0x24 (36) | 5 | Type reference or property ID |
| 0x23 (35) | 2 | Special marker |
| 0x14 (20) | 1 | Special marker |
| 0x21 (33) | 1 | Special marker |

#### PREFIX_173C Clustering (Block 3)

PREFIX_173C exhibits notable clustering behavior:

- Appears at only **two locations** in Block 3: offset `0x1117` and `0x1C60`
- Dense clusters with minimal intervening bytes suggest **array elements** or **repeated structures**
- The pattern `17 3C 00 00 00 00` at offset `0x116F` may indicate a **null/terminator** encoding

## TABLE_REF Format (0x0803)

The most important prefix for understanding the compact format:

```
08 03 [table_id] [prop_id]

08 03 = Prefix (field 1, varint + value 3)
table_id = 1-byte table ID (maps to type hash)
prop_id = 1-byte property index within the type
```

### Example

```
08 03 5E B6 = TABLE_REF(table=0x5E, prop=0xB6)
```

This references property 0xB6 (182) of the type mapped to table ID 0x5E (94).

## Table ID Catalog

### Block 3 Table IDs

| Table ID | Decimal | References | Property Range | Unique Props |
|----------|---------|------------|----------------|--------------|
| 0x08 | 8 | 1 | 0x00 | 1 |
| 0x14 | 20 | 3 | 0x05-0xC2 | 2 |
| 0x17 | 23 | 2 | 0x3C | 1 |
| 0x19 | 25 | 2 | 0x07 | 1 |
| 0x3B | 59 | 1 | 0xC9 | 1 |
| 0x5B | 91 | 4 | 0x03-0xB6 | 4 |
| 0x5D | 93 | 1 | 0xAA | 1 |
| 0x5E | 94 | 63 | 0x01-0xD9 | 42 |
| 0xDB | 219 | 2 | 0x17 | 1 |
| 0xFB | 251 | 1 | 0x0B | 1 |

### Block 5 Table IDs

| Table ID | Decimal | References | Property Range | Unique Props |
|----------|---------|------------|----------------|--------------|
| 0x14 | 20 | 3 | 0x05 | 1 |
| 0x17 | 23 | 2 | 0x3C | 1 |
| 0x19 | 25 | 2 | 0x07 | 1 |
| 0x95 | 149 | 1 | 0x14 | 1 |
| 0xDB | 219 | 1 | 0x17 | 1 |
| 0xE1 | 225 | 1 | 0x19 | 1 |

### Known Table ID Mappings

From binary analysis of ACBSP.exe (see type_table_analysis.json):

| Table ID | Type Hash | Type Name | Props |
|----------|-----------|-----------|-------|
| 0x08 (8) | 0xC9A5839D | CompactType_08 | 22 |
| 0x0B (11) | 0x82A2AEE0 | CompactType_0B | 22 |
| 0x16 (22) | 0x2DAD13E3 | PlayerOptionsElement | - |
| 0x20 (32) | 0xFBB63E47 | World | 14 |
| 0x38 (56) | 0xFA1AA549 | CompactType_38 | 22 |
| 0x3B (59) | 0xFC6EDE2A | CompactType_3B | 22 |
| 0x4F (79) | 0xF49BFD86 | CompactType_4F | 22 |
| 0x5B (91) | 0xC8761736 | CompactType_5B | 22 |
| **0x5E (94)** | **0x0DEBED19** | **CompactType_5E** | **22** |
| 0x5F (95) | 0x938F78BA | CompactType_5F | 22 |

Note: Compact types all inherit from CommonParent (0x7E42F87F) and have 22 properties each.

## Marker Bytes

Single-byte markers appear between TABLE_REF sequences to indicate values or flags:

| Marker | Block 3 Count | Block 5 Count | Likely Meaning |
|--------|---------------|---------------|----------------|
| 0x6D | 41 | 32 | Boolean TRUE or value 1 |
| 0xDB | 35 | 28 | Boolean FALSE or value 0 |
| 0xCD | 19 | 11 | Unknown flag/separator |

### Marker Pattern

Markers typically follow immediately after a TABLE_REF:

```
08 03 5E C1 DB 08 03 5E CA
           ^^ MARKER_DB after prop 0xC1

08 03 5E 96 6D 08 03 5E BB
           ^^ MARKER_6D after prop 0x96
```

## Table 0x5E Deep Analysis

Table 0x5E is the dominant type in Block 3 with 63 references across 42 unique properties:

### Property Groups

| Range | Count | Description |
|-------|-------|-------------|
| 0x01, 0x05 | 2 | Early properties |
| 0x34-0x35 | 2 | Mid-range group 1 |
| 0x37-0x38, 0x3A | 3 | Mid-range group 2 |
| 0x6C | 1 | Isolated property |
| 0x90, 0x96 | 2 | High-range start |
| 0x9D-0x9E | 2 | Status group |
| 0xA0-0xAD | 12 | Primary data block |
| 0xAF | 1 | Gap property |
| 0xB2-0xB8 | 7 | Secondary data block |
| 0xBB, 0xBE, 0xC1, 0xC4, 0xCA | 5 | Flags/config |
| 0xD0, 0xD3, 0xD6, 0xD9 | 4 | End group |

### Complete Property Index List (Reference Data)

The following 42 unique property indices were observed for Table 0x5E in Block 3:

```
0x01, 0x05, 0x34, 0x35, 0x37, 0x38, 0x3A, 0x6C,
0x90, 0x96, 0x9D, 0x9E, 0xA0, 0xA2, 0xA3, 0xA4,
0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xAB, 0xAC,
0xAD, 0xAF, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7,
0xB8, 0xBB, 0xBE, 0xC1, 0xC4, 0xCA, 0xD0, 0xD3,
0xD6, 0xD9
```

**Nibble Distribution Statistics:**
- Low nibbles (prop_id & 0x0F): All 16 values present (0x0-0xF)
- High nibbles (prop_id >> 4): 8 values present (0, 3, 6, 9, A, B, C, D)

**Note:** The nibble extraction code for these property indices has NOT been located in Ghidra analysis. The distribution pattern is documented here as observational data only. See "Future Research" section for investigation status.

## Value Prefixes

### VALUE_1500 Format

```
15 00 [4 bytes little-endian value]

Example: 15 00 08 A5 10 A6 = value 0xA610A508
```

Total: 6 bytes

### VALUE_1200 Format

```
12 00 [4 bytes little-endian value]

Example: 12 00 05 E9 EA E2 = value 0xE2EAE905
```

Total: 6 bytes

Note: The first byte after prefix (0x08 or 0x05) appears to be part of the encoding, not a separate field.

## Data Stream Structure

After the preamble, the data region consists of interleaved:

1. **Property References**: TABLE_REF patterns pointing to specific type properties
2. **Value Markers**: Single bytes indicating boolean/flag values
3. **Prefixed Values**: 2-byte prefix + data for typed values
4. **Raw Data Bytes**: Additional value data between structured entries

### Example Trace (Block 3, offset 0x4E)

```
004E: TABLE_REF(table=0x5B, prop=0x8A)
0052: TABLE_REF(table=0x5E, prop=0xB6)
0056: BYTE(0x8D)
0057: TABLE_REF(table=0x5E, prop=0x90)
005B: TABLE_REF(table=0x5E, prop=0x96)
005F: MARKER_6D
0060: TABLE_REF(table=0x5E, prop=0xBB)
0064: TABLE_REF(table=0x5E, prop=0xBE)
0068: TABLE_REF(table=0x5E, prop=0xC1)
006C: MARKER_DB
006D: TABLE_REF(table=0x5E, prop=0xCA)
```

## Block Content Hypothesis

Based on structural analysis:

### Block 3 (7,972 bytes)

- Heavy use of Table 0x5E suggests a large game object with many properties
- High TABLE_REF density indicates complex nested object structure
- PREFIX_1C04 prevalence (62 occurrences) suggests specific data type handling
- Likely contains: Mission state, inventory, or world object data

### Block 5 (6,266 bytes)

- Fewer TABLE_REFs suggests more direct value storage
- Larger preamble (267 bytes) contains initialization data
- Balanced VARINT/FIXED32 usage suggests numeric data
- Likely contains: Player stats, game progress, or configuration data

## Comparison to Blocks 2/4

| Aspect | Blocks 1/2/4 (Full Format) | Blocks 3/5 (Compact Format) |
|--------|----------------------------|----------------------------|
| Compression | LZSS compressed | Uncompressed |
| Type encoding | Raw 4-byte hashes | 1-byte table IDs |
| Property encoding | Offset-based | Index-based |
| Size | 283 / 32KB / 32KB (decompressed) | 7.9KB / 6.3KB |
| Format deserializer | `FUN_01711ab0` (Block 2) | PropertyData via `FUN_01b11a50` |
| Content header | 10 null bytes + type hash | Version prefix (0x01) + size + flags |
| Entry point | vtable[10] dispatch | PropertyData version dispatch |

## TYPE_REF Format (FUN_01af6a40)

The TYPE_REF dispatcher at `FUN_01af6a40` (offset `+0x16f6a40`) handles type references using a prefix byte:

### Prefix Byte Dispatch

| Prefix | Format | Description |
|--------|--------|-------------|
| `0x00` | Full object | Nested deserialization with full object data |
| `0x01` | Type reference | Validation + sub-type byte + 4-byte type hash |
| `>= 0x02` | Simple reference | Direct object lookup by reference ID |

### Type Reference Structure (Prefix 0x01)

```
01 [sub_type] [type_hash: 4 bytes LE]

Example: 01 05 5E 41 98 0D
         |  |  |
         |  |  +-- Type hash: 0x0D98415E
         |  +-- Sub-type byte
         +-- Prefix: type reference
```

### Full Object Structure (Prefix 0x00)

```
00 [object_data...]

The object data is recursively deserialized using the same pipeline.
```

### Simple Reference Structure (Prefix >= 0x02)

```
[ref_id]

Where ref_id >= 2. The object is looked up from a reference table.
```

## Implementation Notes

### Reading TABLE_REF

```python
def read_table_ref(data, pos):
    if data[pos] == 0x08 and data[pos+1] == 0x03:
        table_id = data[pos+2]
        prop_id = data[pos+3]
        return (table_id, prop_id), pos+4
    return None, pos
```

### Reading VALUE_1500

```python
def read_value_1500(data, pos):
    if data[pos] == 0x15 and data[pos+1] == 0x00:
        value = struct.unpack('<I', data[pos+2:pos+6])[0]
        return value, pos+6
    return None, pos
```

## Known Type Hashes (Reference)

From `sav_parser.py` TYPE_HASHES dictionary:

| Hash | Type Name |
|------|-----------|
| 0xFBB63E47 | World |
| 0x2DAD13E3 | PlayerOptionsElement |
| 0x0984415E | PropertyReference |
| 0xA1A85298 | PhysicalInventoryItem |
| 0xBDBE3B52 | SaveGame |
| 0x5FDACBA0 | SaveGameDataObject |

## Future Research

### High Priority - Nibble Extraction Hunt (PAUSED)

**December 30, 2024 Session Results:**

We traced the PropertyData handler chain completely:

```
FUN_01b11a50 (PropertyData version dispatcher)
  → FUN_01b702e0 (Version 1 initializer) - Just sets up 16-byte structure, NO parsing
  → FUN_01b70450 (Version 1 field reader) - Reads PackedInfo/ObjectID/PropertyID via vtable
    → Parser vtable[38] → FUN_01b48b70 → FUN_01b49430 (dispatcher)
      → Stream reader vtable[9] → FUN_01b6f150 (single byte reader, NO nibble logic)
```

**Key Finding:** The TYPE_REF dispatcher (`FUN_01af6a40`) uses 4-byte type hashes, NOT nibble table IDs. The compact format must use a completely different parsing path.

### Unresolved Questions

1. **Where is nibble extraction?** Not in PropertyData handlers or stream readers we traced
2. **Is "PackedInfo" the nibble data?** The field might contain encoded data decoded elsewhere
3. **Alternative code path?** Compact format may bypass the PropertyData handlers entirely
4. **TTD verification needed** - Set breakpoint on `FUN_01aeaf70` (table ID lookup) during Block 3/5 load

### Suggested Next Steps

1. **Examine raw data** - Look at actual bytes at offset 8+ in Block 3/5 for patterns
2. **Search Ghidra** for `SHR reg, 4` and `AND reg, 0x0F` patterns
3. **TTD trace** with breakpoint on FUN_01aeaf70 when Blocks 3/5 are loaded
4. **Check Version 2/3 handlers** - Maybe different version handlers have nibble logic
5. **Cross-reference callers** of FUN_01aeaf70 - find who passes table IDs

### Analyzed Functions (No Nibble Logic Found)

| Function | Purpose | Result |
|----------|---------|--------|
| FUN_01b702e0 | Version 1 initializer | Just sets vtable/flags, no parsing |
| FUN_01b70450 | Version 1 field reader | Reads via vtable dispatch |
| FUN_01b48b70 | Parser PackedInfo reader | Wrapper for FUN_01b49430 |
| FUN_01b49430 | Parser dispatcher | Routes to stream reader |
| FUN_01b6f150 | Stream byte reader | Single byte read, no nibble logic |
| FUN_01af6a40 | TYPE_REF dispatcher | Uses 4-byte hashes, not table IDs |
| FUN_01aeb020 | Type hash lookup | Wrapper for FUN_01aead60 |
| FUN_01aead60 | Core type lookup | Table management, no nibble extraction |

### Key Breakpoints for Continued Research

```
# PropertyData path (already traced, no nibble logic)
bp ACBSP+0x1711a50   # PropertyData version dispatcher
bp ACBSP+0x1770de0   # Version 1 handler A (FUN_01b702e0) - TRACED
bp ACBSP+0x1770450   # Version 1 handler B (FUN_01b70450) - TRACED

# Type lookup (need to trace during Block 3/5 load)
bp ACBSP+0x1AEAF70   # Table ID lookup - SET THIS during Block 3/5 load!
bp ACBSP+0x16f6a40   # TYPE_REF dispatcher - uses hashes, not IDs

# Stream readers
bp ACBSP+0x176f150   # Single byte reader (FUN_01b6f150) - TRACED
```

### Lower Priority

4. **Table ID Resolution**: Map remaining table IDs (0x5E, 0x5B, etc.) to type hashes via Ghidra analysis
5. **Prefix Semantics**: Determine exact meaning of PREFIX_1C04, PREFIX_173C, etc.
6. **Preamble Structure**: Decode the preamble format for object initialization
7. **Value Encoding**: Understand the full protobuf-like wire format being used
8. **Cross-Block References**: Investigate how Blocks 3/5 relate to Blocks 2/4

## File Locations

- Block 3 test file: `/tmp/compact_analysis/sav_block3_raw.bin`
- Block 5 test file: `/tmp/compact_analysis/sav_block5_raw.bin`
- Parser implementation: `/mnt/f/ClaudeHole/assassinscreedsave/sav_parser.py`
