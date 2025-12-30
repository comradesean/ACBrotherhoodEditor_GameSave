# SAV Deserializer Investigation Handoff

## Session Summary

Traced SAV file loading via WinDbg TTD and Ghidra static analysis to identify block parsers, format deserializers, and the complete parsing pipeline.

---

## Latest Session (December 30, 2024) - Block 2 Collectibles Array Decoded

### Session Goal
Decode the large data array at 0x03E8-0x40D7 in Block 2 (15,600 bytes).

### BREAKTHROUGH: Collectibles Array Structure Identified

**Discovery:** The 15,600-byte array stores 157 collectible entries (100 feathers + 57 flags).

**Entry Structure (98 bytes):**
| Offset | Size | Hash | Purpose |
|--------|------|------|---------|
| +0x00 | 18 | 0x75758A0E | Class reference |
| +0x12 | 18 | 0x768CAE23 | Parent (World link) |
| +0x24 | 18 | 0x309E9CEF | Instance reference |
| +0x36 | 18 | varies | State value (0x00 = uncollected) |
| +0x48 | 26 | 0x9BD7FCBE | Record type footer |

**Field Format (18 bytes):**
```
[Type:1] [Variant:1] [0x0B:1] [0x00:1] [SubType:1] [0x00:3] [Hash/Value:4] [Padding:6]
```

**Key Findings:**
- 156 entries have state = 0x00 (uncollected)
- 1 entry has state = 0x19 (25) - special marker
- All entries link to World object at 0x0212 via hash 0x768CAE23
- Uses full format serialization (4-byte hashes, byte-aligned)

**Understanding Level Update:**
- Block 2 inner layer: **50% -> 70%**
- Collectibles array (15.6 KB / 47.6% of Block 2) now DECODED

### Documentation Updated
- BLOCK2_GAME_STATE_STRUCTURE.md - Collectibles array section
- SAV_BLOCKS_OVERVIEW.md - Cross-reference and collectibles summary
- HANDOFF_SAV_DESERIALIZERS.md - This session note

---

## Previous Session (December 30, 2024) - Complete Block Analysis & Parser Implementation

### Session Goals
1. Analyze Block 3 and Block 5 binary structure
2. Investigate nested headers and cross-block references
3. Analyze Block 4 inventory structure
4. Build working Judy Array deserializer

### MAJOR ACHIEVEMENTS

#### 1. Nested Header Discovery

**Block 3 (7,972 bytes) - 4 Nested Regions:**
| Region | Header Offset | Declared Size | Actual Size | Purpose |
|--------|---------------|---------------|-------------|---------|
| 1 | 0x0000 | 3,641 bytes | 3,641 bytes | Primary CompactType_5E objects (72 TABLE_REFs) |
| 2 | 0x0E46 | 1,877 bytes | 1,877 bytes | PhysicalInventoryItem references |
| 3 | 0x15A8 | 2,402 bytes | 2,402 bytes | Numeric counters (highest VARINT density) |
| 4 | 0x1F17 | 2,150 bytes | **5 bytes** | **CROSS-BLOCK REFERENCE** |

**Block 5 (6,266 bytes) - 2 Nested Regions:**
| Region | Header Offset | Declared Size | Actual Size | Purpose |
|--------|---------------|---------------|-------------|---------|
| 1 | 0x0000 | 1,879 bytes | 1,879 bytes | PropertyReference data |
| 2 | 0x0764 | 2,317 bytes | **4,366 bytes** | Extended data + **growth buffer** |

#### 2. Cross-Block Reference Discovery

**Block 3 Region 4 → Block 4:**
- Region 4 declares 2,150 bytes but contains only 5 bytes
- Block 4's LZSS compressed size = **2,150 bytes** (EXACT MATCH)
- Region 4 is a **reference descriptor** pointing to Block 4
- Descriptor bytes: `00 27 a6 62 20`

**Block 5 Region 2 Growth Buffer:**
- Declared: 2,317 bytes, Actual: 4,366 bytes
- **+2,049 bytes** pre-allocated for dynamic game data

#### 3. 5-Byte Inter-Region Gap Format

All gaps between regions follow this structure:
```
[type_byte] [value_16 LE] [terminator_16 = 0x0020]
```

| Gap | Location | Bytes | Type | Value |
|-----|----------|-------|------|-------|
| Block 3: 1→2 | 0x0E41 | `04 74 62 20 00` | 0x04 | 25,204 |
| Block 3: 2→3 | 0x15A3 | `00 00 28 20 00` | 0x00 | 10,240 |
| Block 3: 3→4 | 0x1F12 | `00 00 a7 20 00` | 0x00 | 42,752 |
| Block 5: 1→2 | 0x075F | `00 00 e5 20 00` | 0x00 | 58,624 |

#### 4. Judy Encoder Functions Analyzed

Decompiled FUN_01b24720 and FUN_01b249a0 from Ghidra:

**FUN_01b24720 (Multi-type encoder):**
| Type | Key Size | Entry Count | Description |
|------|----------|-------------|-------------|
| 0x14 | 1 byte | `[+4] + 1` | Linear leaf (variable) |
| 0x17 | 2 bytes | bitmap | Bitmap branch (up to 256) |
| 0x18 | 2 bytes | 1 | Single entry leaf |
| 0x1b | 1 byte | 2 | 2-element leaf |
| 0x1c | 1 byte | 3 | 3-element leaf |

**FUN_01b249a0 (3-byte key encoder):**
| Type | Key Size | Entry Count | Description |
|------|----------|-------------|-------------|
| 0x15 | 3 bytes | `[+4] + 1` | Linear leaf |
| 0x19 | 3 bytes | 1 | Single 3-byte entry |

**Serialized Output Format:**
```
[type_byte] [count/flags] [keys...] [values...]
```

#### 5. Complete Judy Node Prefix Census

| Prefix | Block 3 | Block 5 | Total | Purpose |
|--------|---------|---------|-------|---------|
| `14 05` | 83 | 58 | 141 | Variable-length integer (VARINT) |
| `08 03` | 80 | 10 | 90 | TABLE_REF (type + property) |
| `05 02` | 75 | 66 | 141 | 32-bit fixed value (FIXED32) |
| `1c 04` | 62 | 1 | 63 | Variable-size leaf (3-element) |
| `12 00` | 47 | 34 | 81 | Linear leaf variant |
| `15 00` | 44 | 11 | 55 | Linear leaf (3-byte keys) |
| `17 3c` | 32 | 32 | 64 | Conditional/bitmap handling |
| `19 07` | 31 | 34 | 65 | Null/empty branch |
| `16 e1` | 22 | 21 | 43 | 3-byte key leaf |
| `18 09` | 19 | 0 | 19 | Null/empty leaf |

#### 6. Block 4 Investigation

**Structure:**
- **Size:** 32,768 bytes (32 KB decompressed)
- **Format:** Full format (4-byte type hashes) - NOT compact
- **Header:** 10 zero bytes only (NO 44-byte header)
- **Items:** 364 PhysicalInventoryItem entries (type hash 0xA1A85298)

**Two Item Formats (Interleaved):**
| Format | Marker (+04) | Count | Size Range | Total Bytes |
|--------|--------------|-------|------------|-------------|
| Format 1 | 0x0032 | 182 | 66-71 bytes | 12,381 |
| Format 2 | 0x0000 | 182 | 22-1,236 bytes | 20,306 |

**Key findings:**
- All Format 1 items have quantity = 42 (max stack?)
- Largest single item: 1,236 bytes
- FORMAT 1 has 1:1 PropertyReference binding
- TYPE_REF pattern: `12 00 0B [4-byte hash]` (369 occurrences)

#### 7. Updated compact_format_parser.py

Implemented Judy Array deserializer with:
- **Region detection** - Finds all 8-byte headers automatically
- **Gap detection** - Parses 5-byte inter-region gaps
- **Cross-block detection** - Identifies when declared >> actual size
- **Judy node parsing** - Decodes types 0x14, 0x15, 0x17, 0x18, 0x19, 0x1B, 0x1C

**New command-line options:**
- `--regions` / `-r` - Shows region breakdown
- `--judy` / `-j` - Shows Judy node decoding
- `--json FILE` - Exports structured JSON

**Test results:**
```
Block 3: 4 regions, 85 Judy nodes, 66 TABLE_REFs
Block 5: 2 regions, 76 Judy nodes, 1 TABLE_REF
```

#### 8. Structural Completeness Review

**SAV File (18,503 bytes) - 100% Outer Layer Complete:**
```
0x0000-0x00D8   Block 1: 44-byte header + 173 LZSS (→ 283 bytes)
0x00D9-0x0842   Block 2: 44-byte header + 1,854 LZSS (→ 32 KB)
0x0843-0x2766   Block 3: 7,972 raw (compact format)
0x2767-0x2FCC   Block 4: 2,150 LZSS, NO header (→ 32 KB)
0x2FCD-0x4846   Block 5: 6,266 raw (compact format)
```

**Per-Block Understanding:**
| Block | Outer Layer | Inner Layer | Overall |
|-------|-------------|-------------|---------|
| 1 | Complete | 85% | MOSTLY COMPLETE |
| 2 | Complete | **70%** | **GOOD** (collectibles decoded) |
| 3 | Complete | 40% | PARTIAL |
| 4 | Complete | 55% | PARTIAL |
| 5 | Complete | 35% | PARTIAL |

### Documentation Updated This Session

- **BLOCKS_3_5_COMPACT_FORMAT.md** - Nested headers, Judy encoders, prefix census
- **SAV_BLOCKS_OVERVIEW.md** - Cross-block references, region structure
- **BLOCK4_INVENTORY_STRUCTURE.md** - Format 1/2, item structure, TYPE_REF pattern
- **CLAUDE.md** - Judy encoder functions, type routing table

### Remaining Gaps

1. **Property hash meanings** - Can't interpret most values
2. **Item ID -> game item mapping** - Can't identify inventory items
3. ~~**Block 2 large data array** (15.6 KB) - ~50% unknown~~ **SOLVED - Collectibles array**
4. **130 entity entries** in Block 2 (0x4B86-0x7FFF) - Purpose unknown
5. **PropertyReference binding** - Not fully traced

### Next Steps

1. **Map property hashes** to field names (need game string database)
2. **Cross-reference item IDs** with game database
3. ~~**Analyze Block 2** large data array (0x03E8-0x40D7)~~ **DONE - Collectibles**
4. **Analyze Block 2 entity array** (0x4B86-0x7FFF) - 130 entries, unknown purpose
5. **Trace PropertyReference bindings** across blocks
6. **Build unified SAV parser** combining all block formats

---

## Previous Session (December 30, 2024) - Judy Array Encoder Discovery

### Session Goal
Find the compact format parser for Blocks 3 and 5.

### BREAKTHROUGH: FUN_01b25230 Confirmed in Compact Format Path

**Breakpoint `bp ACBSP+0x1725230` HITS during Block 3/5 loading!**

This function is a **Judy Array encoder/compressor** - identified by the embedded string:
```
"JudyLMallocSizes = 3, 5, 7, 11, 15, 23, 32, 47, 64, Leaf1 = 25"
```

Judy arrays are highly efficient sparse array data structures used for property storage.

### Trace Results

```
Type normalizer: input type=13
EBX=f86c025c data=0c012110 type=13

0:000> db ebx L8
f86c025c: 10 21 01 0c 00 00 00 13    .!......
```

**8-Byte Input Structure:**
```
Offset  Size  Description
+0x00   4     Data pointer/value (0x0c012110)
+0x04   3     Additional data/flags (0x000000)
+0x07   1     Type tag (0x13)
```

### Call Stack Analysis

```
Frame  Offset       Ghidra VA    Purpose
0      +0x1725230   0x01B25230   FUN_01b25230 - Judy Array encoder
1      +0x1725d66   0x01B25D66   Caller (recursive or orchestrator)
2      +0x17268f1   0x01B268F1   Higher-level caller
3      +0x16fca01   0x01AFCA01   Intermediate
4      +0x16fbb00   0x01AFBB00   Intermediate
5      +0x16eac06   0x01AEAC06   Near FUN_01AEAD60 (core type lookup)
6      +0x16eaf00   0x01AEAF00   Near FUN_01AEAF70 (table ID lookup)
7      +0x16eafdf   0x01AEAFDF   Within FUN_01AEAF70
```

**Key Finding:** Frames 5-7 are within/near FUN_01AEAF70 - the table ID lookup function. This confirms the compact format uses the table ID system through the Judy Array encoder.

### FUN_01b25230 - Type Normalization

This function switches on `byte [input+7] - 0x0B` (types 0x0B through 0x1C) and normalizes them to canonical output types:

| Case | Input Type | Output Type | Description |
|------|------------|-------------|-------------|
| 0 | 0x0B | 0x15 | Linear leaf (2-byte keys + 4-byte values) |
| 1 | 0x0C | 0x16 | Linear leaf (3-byte keys + 4-byte values) |
| 2 | 0x0D | recursive | Index lookup |
| 3 | 0x0E | 0x15 | Bitmap branch (2-byte) |
| 4 | 0x0F | 0x16 | Bitmap branch (3-byte) |
| 5 | 0x10 | recursive | Bitmap lookup |
| 6 | 0x11 | 0x15 | Full 256-element array (2-byte) |
| 7 | 0x12 | 0x16 | Full 256-element array (3-byte) |
| 8 | 0x13 | recursive | **Index lookup** (traced case) |
| 9 | 0x14 | 0x1C | Variable-size leaf |
| 10 | 0x15 | 0x16/0x19 | Passthrough or conversion |
| 11 | 0x16 | 0x1A | Packed 3-byte leaf |
| 12 | 0x17 | varies | Conditional |
| 13 | 0x18 | 0x08 | Null/empty leaf |
| 14 | 0x19 | 0x09 | Null/empty branch |
| 15 | 0x1A | 0x0A | Null marker |
| 16 | 0x1B | 0x18 | 2-element lookup |
| 17 | 0x1C | decrement | Shrink operation |

### Connection to Compact Format Prefixes

The output types from FUN_01b25230 correspond to the compact format prefix bytes:

| Prefix | First Byte | Judy Node Type |
|--------|------------|----------------|
| `15 00` | 0x15 | Linear leaf (VALUE_1500) |
| `12 00` | 0x12 | Intermediate type → 0x18 |
| `18 09` | 0x18 | Null/empty leaf |
| `16 E1` | 0x16 | 3-byte key leaf |
| `19 07` | 0x19 | Null/empty branch |
| `1C 04` | 0x1C | Variable-size |

### Helper Functions Called by FUN_01b25230

| Function | Purpose |
|----------|---------|
| FUN_01b1ea70 | Allocate 0x2a (42) element array |
| FUN_01b1eac0 | Allocate 0x24 (36) element array |
| FUN_01b1ebc0 | Allocate smaller arrays |
| FUN_01b1d880 | Free/deallocate memory |
| FUN_01b1d8c0 | Another deallocation function |
| FUN_01b24720 | Recursive encoding (type 0x15/0x18 output) |
| FUN_01b249a0 | Recursive encoding (type 0x16/0x19 output) |
| FUN_01b61640 | Search/lookup in Judy structure |
| FUN_01b61680 | Another search function |
| FUN_01b1d990 | Population count / bit manipulation |
| FUN_01b1d9f0 | Bit manipulation utility |

### What This Means

1. **Compact format IS Judy arrays** - Blocks 3 and 5 store property data as serialized Judy arrays
2. **Type prefixes are node types** - The 2-byte prefixes identify Judy node types in the stream
3. **TABLE_REF (08 03) remains separate** - This is the table ID + property ID reference format
4. **Multi-pass normalization** - The function loops until type stabilizes (not in 0x0B-0x1C range)

### Next Steps

1. **Examine FUN_01b24720 and FUN_01b249a0** - These write actual value data
2. **Trace caller at +0x1725d66** - Understand how 8-byte structures are populated
3. **Map all Judy node types** to observed binary patterns
4. **Build Judy array parser** for complete Block 3/5 decoding

### Key Breakpoints for Continued Research

```
# Judy Array encoder (CONFIRMED TO HIT)
bp ACBSP+0x1725230 ".printf \"Type=%02x Data=%08x\\n\", byte([ebx+7]), dwo(ebx); g"

# Helper functions
bp ACBSP+0x1724720  # FUN_01b24720 - type 0x15/0x18 encoder
bp ACBSP+0x17249a0  # FUN_01b249a0 - type 0x16/0x19 encoder

# Caller analysis
bp ACBSP+0x1725d66  # Immediate caller return address
```

---

## Previous Session (December 30, 2024) - Nibble Extraction Hunt

### Session Goal
Find where nibble-encoded table IDs are extracted from compact format data (Blocks 3, 5).

### What We Traced

We followed the PropertyData handler chain deep into the engine:

```
FUN_01b11a50 (PropertyData version dispatcher)
  → FUN_01b702e0 (Version 1 initializer) - Just sets up 16-byte structure
  → FUN_01b70450 (Version 1 field reader) - Reads PackedInfo, ObjectID, PropertyID
    → Parser vtable[38] at offset 0x98 → FUN_01b48b70
      → FUN_01b49430 (Parser dispatcher)
        → Stream reader vtable[9] at offset 0x24 → FUN_01b6f150 (single byte reader)
```

### Key Discoveries

1. **FUN_01b702e0** is NOT a parser - it's a simple initializer:
   ```c
   struct PropertyDataObject {  // 16 bytes
       void* vtable;      // +0x00: 0x025561ec → 0x01b71d70
       byte  flags;       // +0x04: (param << 2) | 1
       uint  PackedInfo;  // +0x08
       uint  ObjectID;    // +0x0C
   };
   ```

2. **FUN_01b70450** reads three fields via vtable dispatch:
   - "PackedInfo" via vtable[38] → stored at +0x04
   - "ObjectID" via vtable[39] → stored at +0x08
   - "PropertyID" via vtable[33] → stored at +0x0C

3. **Stream Reader Architecture** (vtable at 0x02556168):
   - Created by FUN_01b6f730 (factory) → FUN_01b6f590 (constructor)
   - 0x38-byte object with stream position tracking
   - vtable[9] (offset 0x24) = FUN_01b6f150 - reads single byte
   - vtable[15] (offset 0x3c) = FUN_01b6f370 - writes single byte

4. **FUN_01af6a40 (TYPE_REF Dispatcher)** - Uses 4-byte type hashes, NOT nibble table IDs:
   ```c
   prefix = read_byte();
   if (prefix == 0x00) {
       skip(1);
       type_hash = read_uint32();  // 4-byte hash
       FUN_01aeb020(type_hash, 0);
       // ... full object deserialization
   } else if (prefix == 0x01) {
       sub_type = read_byte();
       type_hash = read_uint32();  // 4-byte hash
       // ... type reference with validation
   } else {
       // >= 0x02: simple reference
   }
   ```

5. **Type Lookup System**:
   - FUN_01aeaf70: Takes table ID directly
   - FUN_01aeb020: Takes type hash, wraps FUN_01aead60
   - FUN_01aead60: Core lookup (handles both), calls FUN_01aea0b0
   - Table at manager+0x98, count at manager+0x9e (& 0x3FFF)
   - Each bucket: 12 bytes, each entry: 16 bytes

### Critical Insight: Two Different Formats

| Format | Data Type | Lookup Function | Used By |
|--------|-----------|-----------------|---------|
| Full Format | 4-byte type hash | FUN_01aeb020 | Blocks 1, 2, 4 via FUN_01af6a40 |
| Compact Format | Nibble table ID | FUN_01aeaf70 | Blocks 3, 5 (path unknown) |

The TYPE_REF dispatcher (FUN_01af6a40) handles **full format only**. The compact format nibble extraction must be in a completely separate code path that we haven't found yet.

### Why We Haven't Found Nibble Extraction

1. The PropertyData handlers we traced just read raw bytes via vtable dispatch
2. FUN_01b6f150 is a simple single-byte reader - no nibble logic
3. The vtable chain ends at basic byte I/O, not nibble processing
4. The "PackedInfo" field might BE the nibble-encoded data (read as raw bytes, decoded elsewhere)

### Status: PAUSED

**Pinned for later investigation.** The nibble extraction for compact format (Blocks 3, 5) remains unfound.

### Next Steps When Resuming

1. **Examine raw compact format data** - Look at actual bytes at offset 8+ in Block 3/5
2. **Search for nibble patterns** in Ghidra: `SHR reg, 4` and `AND reg, 0x0F`
3. **Try TTD tracing** with breakpoint on FUN_01aeaf70 during Block 3/5 load
4. **Check if "PackedInfo" contains nibble data** that's decoded after reading
5. **Look for alternative PropertyData paths** - maybe version 2 or 3 handlers?

---

## Previous Session (December 2024)

### Critical Corrections

**The format dispatcher address was INCORRECT:**
- `0x01B298A0` / offset `+0x17298a0` - This address does NOT hit during SAV loading
- The real TYPE_REF dispatcher is `FUN_01af6a40` at offset `+0x16f6a40`

### TTD-Verified Findings

1. **CAFE00 Deserializer** (`FUN_01711ab0` at runtime `ACBSP+0x1311ab0`):
   - Validates `type == 1` and `magic == 0x00CAFE00`
   - Only Block 2 goes through the vtable[10] dispatch
   - Blocks 3 and 5 do NOT hit this dispatcher

2. **TYPE_REF Format** (`FUN_01af6a40`):
   - Prefix byte `0x00`: Full object with nested deserialization
   - Prefix byte `0x01`: Reference with type validation + sub-type byte + 4-byte type hash
   - Prefix byte `>= 0x02`: Simple object reference

3. **Compact Format Discovery**:
   - Blocks 3 and 5 are NOT processed through the main block deserializer vtable dispatch
   - They appear to be processed as **PropertyData** within another block
   - `FUN_01b11a50` handles PropertyData with version checks for 0x01, 0x02, 0x03
   - These version bytes match the compact format header!

4. **PropertyData Handlers**:
   - Version 1: `FUN_01b702e0`, `FUN_01b70450`
   - Version 2: `FUN_01b70380`, `FUN_01b704f0`
   - Version 3: `FUN_01b71200`, `FUN_01b709a0`

## CRITICAL: Address Mapping

**Previous handoff had incorrect addresses.** WinDbg offsets were recorded as Ghidra VAs.

| Base | Value | Description |
|------|-------|-------------|
| WinDbg runtime | varies (e.g., `0x00F30000`) | Module base at runtime (ASLR) |
| Ghidra static | `0x00400000` | Default analysis base |

**Conversion Formula:**
```
Ghidra VA = 0x400000 + WinDbg offset
WinDbg offset = Runtime VA - Module Base
```

**Example:**
- WinDbg shows `ACBSP+0x1711ab0`
- Ghidra VA = `0x400000 + 0x1711ab0` = `0x01B11AB0`

## What We Found

### SAV Loading Call Chain
```
SaveGameManager::LoadSavSlot (FUN_0046d7b0)
  → FUN_0046d430 (Block Parser) - validates 0x16/0xFEDBAC, iterates blocks
    → vtable[10] dispatch → FUN_01B11AB0 (CAFE00 deserializer for Block 2)
      → FUN_01AFD600 (Main deserializer orchestrator)
        → FUN_01B0A740 (Object extraction)
          → FUN_01B08CE0 (ObjectInfo metadata parser)
```

### Complete Parsing Pipeline

| Ghidra VA | Offset | Size | Purpose |
|-----------|--------|------|---------|
| `0x01B7A1D0` | `+0x17B7A1D0` | - | OPTIONS magic detector (`0x57FBAA33`, `0x1004FA99`) |
| `0x01B7B190` | `+0x17B7B190` | - | OPTIONS-style header decompressor (32KB chunks) |
| `0x01B6F730` | `+0x1B6F730` | 0x38 | Creates stream reader object |
| `0x01B49250` | `+0x1B49250` | 0x1058 | Creates parser object (vtable at `0x02555C60`) |
| `0x01AEDD90` | `+0x1AEDD90` | 0x12D8 | Pushes parser state onto stack |
| `0x01AFD600` | `+0x1AFD600` | - | **Main deserializer orchestrator** |
| `0x01B0A740` | `+0x1B0A740` | - | Object extraction/deserialization |
| `0x01B08CE0` | `+0x1B08CE0` | - | ObjectInfo metadata parser |
| `0x00425360` | `+0x0025360` | - | Buffer descriptor setter (NOT a parser) |

### CAFE00 Deserializer: FUN_01B11AB0

Ghidra VA `0x01B11AB0` (offset `+0x1711AB0`):

```c
if (type == 1 && magic == 0x00CAFE00) {
    // Skip 8-byte header (piVar1 + 2)
    FUN_00425360(buffer_desc, data+8, size-8, ...);  // Set up buffer
    result = FUN_01AFD600(buffer_desc);               // Parse data
    if (result != NULL) {
        (*vtable[0x0C])(result, 0);                   // Finalize object
        return 1;
    }
}
return 0;
```

### Parser Vtable at 0x02555C60

The parser object created by `FUN_01B49250` uses this vtable:

| Offset | Slot | Ghidra VA | Purpose |
|--------|------|-----------|---------|
| 0x00 | 0 | `0x01B49B10` | Constructor/base |
| 0x08 | 2 | `0x01B48770` | BeginElement |
| 0x10 | 4 | `0x01B487A0` | EndElement |
| 0x50 | 20 | `0x01B48FB0` | **Read type hash ("T")** |
| 0x54 | 21 | `0x01B48E90` | Read ObjectName |
| 0x84 | 33 | `0x01B48C10` | Read ClassID |
| 0x8C | 35 | `0x01B48C00` | Read Version |
| 0x9C | 39 | `0x01B48E70` | Read ObjectID |

### ObjectInfo Fields (FUN_01B08CE0)

The ObjectInfo metadata parser extracts these fields in order:
1. SerializerVersion
2. ClassVersion
3. NbClassVersionsInfo
4. VersionClassID + Version pairs (repeated)
5. ObjectName
6. ObjectID
7. InstancingMode (`0x01` = child, `0x02` = embedded)
8. FatherID
9. Type hash ("T")

### Table ID Lookup System

**Call chain:**
```
FUN_01AEAF70 (wrapper)
  → FUN_01AEAD60 (table manager)
    → FUN_01AEA0B0 (actual lookup)
```

**Table ID Encoding** (stored at `type_descriptor[+4]`):
```c
raw_value = type_desc[+4] & 0xC3FFFFFF;
table_id = raw_value - 1;
bucket_index = table_id >> 14;       // upper bits
entry_index = table_id & 0x3FFF;     // lower 14 bits, max 16383
address = table[bucket*12] + entry*16;
```

**Table Structure** at `[manager + 0x98]`:
- Count at `[manager + 0x9E]` (masked with `0x3FFF`)
- Each bucket: 12 bytes (3 dwords)
- Each entry: 16 bytes (4 dwords)

### Key Global Data Addresses

| Address | Purpose |
|---------|---------|
| `DAT_02A62B24` | Format byte global (runtime initialized, starts as 0) |
| `DAT_02A5E0F4` | Global allocator/manager pointer |
| `DAT_02A6247C` | Type registry |
| `DAT_02A622A8` | Allocator instance |
| `DAT_02A621A4` | Null handle singleton |
| `DAT_02A621A8` | Null handle reference count |

### Functions That Are NOT Deserializers

**Avoid confusion** - these were investigated but are utility functions:

| Ghidra VA | Purpose |
|-----------|---------|
| `0x01ADCC30` | Custom heap `free()` - has `EnterCriticalSection`, block coalescing |
| `0x01ABE690` | Target of JMP at `0x01ADCC30` - the actual heap free |
| `0x01AE44F0` | Simple initializer - just zeros two dwords |
| `0x00425360` | Buffer descriptor setter - sets `[0]=ptr`, `[4]=size`, `[8]=flags` |

### Block Parser: FUN_0046d430

- Validates file header: `[+0x00]=0x16`, `[+0x04]=0xFEDBAC`
- Block array at `SaveSlot+0x3C`, count at `SaveSlot+0x42` (& `0x3FFF`)
- Each block has 4-byte size prefix, then data
- Calls `vtable[10]` on block objects to deserialize

**Important:** Only Block 2 uses `vtable[10]` dispatch directly. Other blocks go through the format dispatcher chain.

### Field3 Values in 44-byte Headers

| Block | Offset | Field3 | Has Header |
|-------|--------|--------|------------|
| Block 1 | 0x0008 | `0x000000CD` | ✓ |
| Block 2 | 0x00E1 | `0x00CAFE00` | ✓ |
| Block 3 | N/A | - | ✗ No header |
| Block 4 | N/A | - | ✗ No header |
| Block 5 | N/A | - | ✗ No header |

### Format Dispatchers (Corrected Addresses)

| Ghidra VA | Offset | Purpose | Status |
|-----------|--------|---------|--------|
| `0x01B298A0` | `+0x17298a0` | Format dispatcher - checks format byte at `[param+8]` | **INCORRECT - Does not hit** |
| `0x01AF6A40` | `+0x16f6a40` | **TYPE_REF dispatcher** - prefix byte routing | **CONFIRMED** |
| `0x01AD5D20` | `+0x16d5d20` | Type vtable dispatcher - calls `vtable[0x14]` | Unverified |

**TYPE_REF Prefix Bytes (FUN_01af6a40):**
| Byte | Description | Handler |
|------|-------------|---------|
| `0x00` | Full object with nested deserialization | Recursive call |
| `0x01` | Type reference with validation + sub-type + 4-byte hash | Validation path |
| `>= 0x02` | Simple object reference | Direct lookup |

**Format Bytes (Header-based):**
| Byte | Description | Used By |
|------|-------------|---------|
| `0x1C` | Block data format | Block 1 |
| `0x01` | Compact format / PropertyData version | Blocks 3, 5 |
| `0x1F` | Type reference format | Type refs |

### Deserializer Functions (Corrected)

| Ghidra VA | Offset | Format | Used By |
|-----------|--------|--------|---------|
| `0x01B11AB0` | `+0x1711ab0` | CAFE00 (type=1, magic=0x00CAFE00) | SAV Block 2 |
| `0x01B12DB0` | `+0x1712db0` | 11FACE11 (type=3, magic=0x11FACE11) | OPTIONS S2 |
| `0x01B109E0` | `+0x17109e0` | 21EFFE22 (type=0, magic=0x21EFFE22) | OPTIONS S3 |
| `0x01B12660` | `+0x1712660` | Raw copy (no magic check) | ? |

### Block Processing Summary

| Block | Format | Deserializer Path | Status |
|-------|--------|-------------------|--------|
| 1 | 0x1C header | Format dispatcher → Type dispatcher → Data deserializer | Unverified |
| 2 | CAFE00 header | vtable[10] → `FUN_01B11AB0` (CAFE00) → `FUN_01AFD600` | **TTD Confirmed** |
| 3 | 0x01 compact | PropertyData handler (`FUN_01b11a50`) → Version 1 handlers | **New Discovery** |
| 4 | LZSS only | Processed within Block 2 or separate path | Unverified |
| 5 | 0x01 compact | PropertyData handler (`FUN_01b11a50`) → Version 1 handlers | **New Discovery** |

### PropertyData Handler (FUN_01b11a50)

Handles PropertyData blocks with version-based dispatch:

```c
switch (version_byte) {
    case 0x01:
        FUN_01b702e0(...);  // or FUN_01b70450
        break;
    case 0x02:
        FUN_01b70380(...);  // or FUN_01b704f0
        break;
    case 0x03:
        FUN_01b71200(...);  // or FUN_01b709a0
        break;
}
```

**Key Insight:** Blocks 3 and 5 start with version byte `0x01`, which matches this dispatch!

## What's Still Unknown

### Nibble-Encoded Table ID Reading

We found how table IDs are **stored and looked up**, but NOT where they are **read from the binary stream**:

- **Found:** Table ID encoding formula, lookup functions
- **Missing:** The actual nibble extraction (`SHR 4`, `AND 0x0F`) from compact format data

The nibble reading is likely in:
1. `FUN_01b702e0` or `FUN_01b70450` - Version 1 PropertyData handlers
2. These are called when the version byte is `0x01` (matching Blocks 3/5 header)

### How PropertyData Blocks Are Linked

- Blocks 3 and 5 are NOT processed through the main block deserializer vtable dispatch
- They appear to be embedded within another block's deserialization (likely Block 2)
- The PropertyData handler at `FUN_01b11a50` receives the raw block data
- The version byte `0x01` routes to the appropriate handler

### Questions Remaining

1. Exact nibble extraction code location (likely in `FUN_01b702e0` or `FUN_01b70450`)
2. How PropertyData blocks are linked to the raw Block 3/5 data
3. Complete table ID to type hash mapping for compact format
4. Is the Raw deserializer (`0x01B12660`) used for any SAV blocks?
5. How is Block 4 (LZSS compressed inventory) processed within the pipeline?

## Where to Continue

### Priority 1: Analyze PropertyData Version 1 Handlers

The nibble extraction is most likely in these functions:

```
bp ACBSP+0x1370de0  # FUN_01b702e0 - Version 1 handler A
bp ACBSP+0x1370450  # FUN_01b70450 - Version 1 handler B
```

Search for nibble extraction patterns in Ghidra:
```
SHR ..., 4      ; extract high nibble
AND ..., 0x0F   ; mask low nibble
```

### Priority 2: Trace PropertyData Dispatch

Set breakpoint on PropertyData handler to see when Blocks 3/5 are processed:
```
bp ACBSP+0x1311a50  # FUN_01b11a50 - PropertyData version dispatcher
```

### Priority 3: Find Block Linkage

Trace when PropertyData with version `0x01` is processed:
- Set conditional breakpoint when first byte of data == 0x01
- Examine call stack to find where Block 3/5 data is fed in

### Deprecated Breakpoints (Do Not Use)

```
# WRONG - This address does not hit during SAV loading:
# bp ACBSP+0x17298A0  # Format dispatcher - INCORRECT
```

### Key Breakpoints (Updated with Correct Offsets)

```
# Block parsing entry points
bp ACBSP+0x46d430    # Block parser entry
bp ACBSP+0x1711ab0   # CAFE00 deserializer (Block 2)

# Main deserializer pipeline
bp ACBSP+0x1AFD600   # Main deserializer orchestrator
bp ACBSP+0x1B0A740   # Object extraction
bp ACBSP+0x1B08CE0   # ObjectInfo metadata parser

# Type system
bp ACBSP+0x1AEAF70   # Table ID lookup
bp ACBSP+0x1AEA0B0   # Actual table lookup
bp ACBSP+0x16f6a40   # TYPE_REF dispatcher (CONFIRMED)

# PropertyData handlers (NEW - for compact format)
bp ACBSP+0x1311a50   # PropertyData version dispatcher
bp ACBSP+0x1370de0   # Version 1 handler A (FUN_01b702e0)
bp ACBSP+0x1370450   # Version 1 handler B (FUN_01b70450)

# DEPRECATED - do not use:
# bp ACBSP+0x1B298A0   # Format dispatcher - DOES NOT HIT
```

### TTD Positions of Interest

- B4A2F: SAVEGAME0 being loaded
- B49F9: Block loop iteration
- D73CB9: Later SAVEGAME0 operations

## Reference Files

```
references/ACBROTHERHOODSAVEGAME0.SAV     # Original SAV
references/sav_block1_decompressed.bin    # Block 1 (SaveGame)
references/sav_block2_decompressed.bin    # Block 2 (World)
references/sav_block3_raw.bin             # Block 3 (compact)
references/sav_block4_decompressed.bin    # Block 4 (Inventory)
references/sav_block5_raw.bin             # Block 5 (compact)
```

## Documentation Updated

- **CLAUDE.md** - Address mapping, parsing pipeline, vtable, table ID system, global data
- **docs/SAV_FILE_FORMAT_SPECIFICATION.md** - Block deserializer functions
- **docs/TYPE_SYSTEM_REFERENCE.md** - Parsing pipeline, table ID encoding
- **docs/blocks/BLOCKS_3_5_COMPACT_FORMAT.md** - Table ID lookup details
