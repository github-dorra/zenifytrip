"""
Process a raw TripAdvisor page text file and save to MongoDB Atlas.
Usage:
  python -m app.scripts.process_saved_text <city_key> <text_file>
  python -m app.scripts.process_saved_text tunis  app/data/tmp/tunis.txt
  python -m app.scripts.process_saved_text tozeur app/data/tmp/tozeur.txt
"""
import sys
from pathlib import Path

def main():
    if len(sys.argv) < 3:
        print("Usage: python -m app.scripts.process_saved_text <city_key> <text_file>")
        sys.exit(1)

    city_key  = sys.argv[1]
    text_file = Path(sys.argv[2])

    if not text_file.exists():
        print(f"File not found: {text_file}")
        sys.exit(1)

    raw_text = text_file.read_text(encoding="utf-8")
    print(f"Read {len(raw_text)} chars from {text_file}")

    from app.scripts.tripadvisor_scraper import save_page_text
    result = save_page_text(city_key, raw_text)
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
