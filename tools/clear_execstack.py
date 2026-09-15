import struct
import sys
from pathlib import Path

PT_GNU_STACK = 0x6474E551
PF_X = 0x1


def clear_executable_stack(path: Path) -> bool:
    try:
        with path.open("r+b") as executable:
            header = executable.read(64)
            if len(header) < 52 or header[:4] != b"\x7fELF":
                return False

            elf_class = header[4]
            byte_order = "<" if header[5] == 1 else ">"
            if elf_class == 2:
                program_offset = struct.unpack_from(f"{byte_order}Q", header, 32)[0]
                entry_size = struct.unpack_from(f"{byte_order}H", header, 54)[0]
                entry_count = struct.unpack_from(f"{byte_order}H", header, 56)[0]
                flags_offset = 4
            elif elf_class == 1:
                program_offset = struct.unpack_from(f"{byte_order}I", header, 28)[0]
                entry_size = struct.unpack_from(f"{byte_order}H", header, 42)[0]
                entry_count = struct.unpack_from(f"{byte_order}H", header, 44)[0]
                flags_offset = 24
            else:
                return False

            for entry_index in range(entry_count):
                entry_offset = program_offset + entry_index * entry_size
                executable.seek(entry_offset)
                entry = executable.read(entry_size)
                segment_type = struct.unpack_from(f"{byte_order}I", entry)[0]
                if segment_type != PT_GNU_STACK:
                    continue
                flags = struct.unpack_from(f"{byte_order}I", entry, flags_offset)[0]
                if not flags & PF_X:
                    return False
                executable.seek(entry_offset + flags_offset)
                executable.write(struct.pack(f"{byte_order}I", flags & ~PF_X))
                return True
    except OSError:
        return False
    return False


def main(arguments: list[str]) -> int:
    if sys.platform != "linux":
        return 0
    root = Path(arguments[0]) if arguments else Path("dist")
    patched = [path for path in root.rglob("*") if path.is_file() and clear_executable_stack(path)]
    for path in patched:
        print(f"Cleared executable-stack flag: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
