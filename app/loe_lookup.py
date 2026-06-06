import argparse
import asyncio
import json

from app.loe_api import lookup_loe_address


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Look up Lvivoblenergo groups for an address.")
    parser.add_argument("--city", required=True, help="City or settlement name, for example: Шкло")
    parser.add_argument("--street", required=True, help="Street name, for example: 1-го Травня")
    parser.add_argument("--building", required=True, help="Building number, for example: 2-А")
    parser.add_argument("--otg-id", type=int, default=None, help="Optional Lvivoblenergo OTG id.")
    parser.add_argument("--debug", action="store_true", help="Show lookup diagnostics.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    result = await lookup_loe_address(
        city_name=args.city,
        street_name=args.street,
        building=args.building,
        otg_id=args.otg_id,
        debug=args.debug,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
