# Atlas test report

## Interactive locations

| Map | Group | Locations |
| --- | --- | --- |
| World of Nirn | Tamriel and provinces | Tamriel, Skyrim, High Rock, Hammerfell, Cyrodiil, Morrowind, Summerset Isles, Valenwood, Elsweyr, Black Marsh |
| World of Nirn | Other lands and islands | Atmora, Akavir, Yokuda, Pyandonea, Solstheim, Vvardenfell |
| World of Nirn | Seas and oceans | Abecean Sea, Eltheric Ocean, Sea of Ghosts, Inner Sea, Padomaic Ocean, Sea of Pearls |
| Skyrim | Holds | Haafingar Hold, Hjaalmarch Hold, The Pale Hold, Winterhold Hold, Eastmarch Hold, Whiterun Hold, The Reach Hold, Falkreath Hold, The Rift Hold |
| Skyrim | Hold capitals | Solitude, Morthal, Dawnstar, Winterhold, Windhelm, Whiterun, Markarth, Falkreath, Riften |
| Skyrim | Province and neighbors | Skyrim, High Rock, Hammerfell, Cyrodiil, Morrowind |
| Skyrim | Other locations | Velothi Mountains, Mogollon Hearth |

**Coverage.** 22 World targets and 25 Skyrim targets serve all 42 research entries. Five entries are shared across the maps. Zero entries were omitted. Compact targets follow printed labels or city markers where the illustrations lack a usable boundary. The Skyrim map’s Mogollon Hearth target leaves room around Riften’s marker. A location picker makes compact labels easier to use on small screens.

## Verification

- **Desktop Chrome.** Clicked all 47 SVG targets and verified the matching heading, two paragraphs, and X dismissal. Checked keyboard activation with Enter and Space, Escape and focus return, the Close button, the location picker, World/Skyrim navigation, reset, and reload into the Skyrim view.
- **Responsive Chrome checks.** Used simulated viewport dimensions and synthetic touch events for tablet and phone checks. The browser checked target hit geometry, card activation, dismissal, aspect ratio, text fit, and hover timing. Touch did not trigger hover. The hover preview opened after approximately 1.5 seconds and disappeared on pointer leave. Physical touch hardware was outside this test.
- **Layout and motion results.** All 47 targets passed at 768×1024, 1024×768, 390×844, and 568×320. Cards fit without internal scrolling in the first three sizes. The short landscape phone viewport scrolled the card body and kept the X in view. Chrome measured 1.2-second opacity transitions for both the outgoing and incoming maps through Explore, Back, the Skyrim shortcut, and Reset.
- **Google Maps.** Both controls opened a separate Chrome tab and used the baseline URL verbatim, including the center, `178373m`, and the satellite layer. Google Maps displayed satellite imagery around Payson and kept the center while rewriting its own zoom to `235412m` in the test browser.
- **Package.** Both WebP files match the baseline byte for byte. All 42 cards contain 101–119 words in two paragraphs. The site uses only relative local asset references and requires no build or runtime service for the atlas. Browser testing used a local preview because the Chrome session disallowed `file://` navigation.

Extract the ZIP and open `World_of_Nirn_Web_App/index.html` in Chrome. Google Maps uses an internet connection.