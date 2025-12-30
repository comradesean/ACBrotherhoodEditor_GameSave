# SAV Deserializer Investigation Handoff

## Session Summary

Traced SAV file loading via WinDbg TTD and Ghidra static analysis to identify block parsers, format deserializers, and the complete parsing pipeline.

## Latest Session (December 30, 2024) - Nibble Extraction Hunt

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
