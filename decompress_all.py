import os
import zstandard as zstd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DICT_PATH = os.path.join(SCRIPT_DIR, "zstd.dict")
PATTERNS_DIR = os.path.join(SCRIPT_DIR, "clock_patterns")

def decompress_all():
    if not os.path.exists(DICT_PATH):
        print(f"[-] Dictionary not found: {DICT_PATH}")
        return

    with open(DICT_PATH, "rb") as f:
        dict_data = f.read()

    d_dict = zstd.ZstdCompressionDict(dict_data)
    dctx = zstd.ZstdDecompressor(dict_data=d_dict)

    print(f"[*] Decompressing patterns in {PATTERNS_DIR}...")
    for fname in sorted(os.listdir(PATTERNS_DIR)):
        if fname.endswith(".binscled.zst"):
            in_path = os.path.join(PATTERNS_DIR, fname)
            out_path = os.path.join(PATTERNS_DIR, fname[:-4]) # strip .zst
            with open(in_path, "rb") as f:
                cdata = f.read()
            try:
                raw_data = dctx.decompress(cdata, max_output_size=10 * 1024 * 1024)
                with open(out_path, "wb") as f_out:
                    f_out.write(raw_data)
                frames = len(raw_data) // 35
                print(f"  [+] {fname:30s} -> {len(raw_data):5d} bytes ({frames:2d} frames)")
            except Exception as e:
                print(f"  [-] Failed {fname}: {e}")

if __name__ == "__main__":
    decompress_all()
