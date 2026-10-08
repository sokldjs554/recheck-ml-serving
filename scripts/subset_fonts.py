"""Rebuild licensed UI font subsets after copy changes (requires fonttools)."""
from argparse import ArgumentParser
from pathlib import Path

from fontTools import subset


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--korean-source", required=True, type=Path)
    parser.add_argument("--latin-source", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    text = "".join(chr(i) for i in range(32, 127))
    for path in sorted((root / "demo/src").rglob("*")):
        if path.suffix in {".ts", ".tsx", ".css"}:
            text += path.read_text()
    for source, name in (
        (args.korean_source, "recheck-korean.woff"),
        (args.latin_source, "recheck-latin.woff"),
    ):
        options = subset.Options()
        options.flavor = "woff"
        font = subset.load_font(str(source), options)
        worker = subset.Subsetter(options=options)
        worker.populate(text=text)
        worker.subset(font)
        target = root / "demo/public/fonts" / name
        subset.save_font(font, str(target), options)
        print(f"Updated {target.relative_to(root)}")


if __name__ == "__main__":
    main()
