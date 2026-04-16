from external_db_handler import check_availability
import json

def test():
    print("Testing 'Teeth Cleaning' for today at 3 PM...")
    res = check_availability("Teeth Cleaning", "2026-04-15T15:00:00Z")
    print(json.dumps(res, indent=2))

    print("\nTesting 'Teeth Cleaning' for today at 5:30 PM (Mona Lisa has a booking)...")
    res = check_availability("Teeth Cleaning", "2026-04-15T17:30:00Z")
    print(json.dumps(res, indent=2))

if __name__ == "__main__":
    test()
