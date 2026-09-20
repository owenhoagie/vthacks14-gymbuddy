# Real VT dining data for the demo

The meal planner uses a committed snapshot of Virginia Tech's FoodPro JSON APIs.
It does not scrape the landing page, invent foods, or estimate nutrition from names.
The snapshot is served by the Next.js `/api/foodpro?hall=15` route. It does not require
credentials, Databricks, Gemini, a scheduler, or requests to VT while visitors browse.

## Included snapshot

Menu date: **September 19, 2026**. The exact capture time is stored in the snapshot
and shown in Eastern Time on the page. These foods were listed for that date;
the saved data does not claim current availability.

| Hall | VT ID | Foods / serving variants | With nutrition |
| --- | --- | --- | --- |
| D2 at Dietrick Hall | 15 | 215 | 213 |
| Hokie Grill at Owens | 09 | 0 | 0 |
| West End at Cochrane Hall | 16 | 127 | 127 |
| Squires Food Court | 18 | 182 | 181 |

A recipe appearing at several meal periods is combined when its hall, recipe ID,
portion size, and portion unit match. Its meal periods and stations remain attached.
VT returned no food items for Hokie Grill on this date. The page says so instead of
substituting a different hall's menu. Three foods lack complete usable nutrition;
they remain searchable but cannot be added to macro totals. Missing values are never
converted to zero. Custom food entries require the user's own nutrition numbers and
are labeled as user-entered. The plate starts empty.

## Sources

- Locations: `https://foodpro.students.vt.edu/menus/API/Locations.aspx`
- Menu: `https://foodpro.students.vt.edu/menus/API/MenuAtLocation.aspx?locationNum=15&dtdate=09%2F19%2F2026`
- Per-serving label: `https://foodpro.students.vt.edu/menus/API/Label.aspx?locationNum=15&dtdate=09%2F19%2F2026&recNumAndPort=141002%2A2`

Each saved food includes its original label URL. Calories, protein, carbohydrates,
and fat come directly from that label for the requested portion. Decimal values are
preserved; only displayed totals are rounded to one decimal. VT also supplies allergen
text, which is retained in the snapshot, but this feature does not assess allergy safety.
These endpoints power VT's website; they are not a documented third-party API contract.

## Manual refresh only

From the repository root, with Python 3.11 or newer:

```sh
python3 scripts/snapshot_dining.py --date 2026-09-19
cd web
npm test
npm run build
```

Choose the desired menu date explicitly. The script fetches four menus and their
nutrition labels with at most three concurrent label requests and bounded retries.
A failed request leaves the existing snapshot intact. A successful run atomically
replaces `web/fixtures/dining-snapshot.json`. Review the data and counts, update this
document and snapshot-specific test expectations, commit the file, and redeploy the
frontend when ready. No automatic refresh is configured.

## Remaining PR work

This change addresses real data and truthful provenance. The previously audited
meal-page dark mode/mobile styling, saved plate persistence, and repeated servings
still need work before the full food feature is ready to merge.
