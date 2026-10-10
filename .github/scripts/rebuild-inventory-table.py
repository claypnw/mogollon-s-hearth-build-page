"""Rebuild the public build-page prop inventory table from the master markdown.

Run automatically by .github/workflows/rebuild-inventory-table.yml on every
push that changes production/hearth-prop-inventory.md, and usable locally:
    python3 .github/scripts/rebuild-inventory-table.py
"""
import html as htmlmod

MD = "production/hearth-prop-inventory.md"
PAGE = "index.html"


def find_photos(cell):
    """Extract photo paths from markdown image tags in a table cell."""
    photos = []
    i = 0
    while True:
        j = cell.find("![", i)
        if j < 0:
            break
        k = cell.find("](", j)
        if k < 0:
            break
        m = cell.find(")", k)
        if m < 0:
            break
        photos.append(cell[k + 2:m])
        i = m + 1
    return photos


with open(MD, encoding="utf-8") as f:
    text = f.read()

rows = []
for line in text.split("\n"):
    t = line.strip()
    if not t.startswith("|"):
        continue
    cells = [c.strip() for c in t.split("|")[1:-1]]
    if len(cells) < 5 or not cells[0].isdigit():
        continue
    rows.append((int(cells[0]), find_photos(cells[1]), cells[2], cells[3], cells[4]))
rows.sort()


def esc(s):
    return htmlmod.escape(s, quote=False)


with open(PAGE, encoding="utf-8") as f:
    page = f.read()

bi = page.find("<tbody>")
ei = page.find("</tbody>")
body_start = page.find("\n", bi) + 1
body_end = page.rfind("\n", 0, ei)
first_row = page.find("<tr>", body_start)
line_start = page.rfind("\n", 0, first_row) + 1
indent = page[line_start:first_row]

new_rows = []
for n, photos, item, use, notes in rows:
    if photos:
        pname = photos[0].split("/")[-1]
        photo_html = (
            '<a href="production/item.html?n=%d">'
            '<img src="props/%s?v=2" alt="Item %d photo" loading="lazy"></a>'
            % (n, pname, n)
        )
    else:
        photo_html = ""
    new_rows.append(
        indent
        + (
            '<tr><td data-v="%d">%d</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
            % (n, n, photo_html, esc(item), esc(use), esc(notes))
        )
    )

newpage = page[:body_start] + "\n".join(new_rows) + page[body_end:]
with open(PAGE, "w", encoding="utf-8") as f:
    f.write(newpage)
print("rebuilt", len(new_rows), "rows")
