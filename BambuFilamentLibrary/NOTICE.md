# Notice / Sources / Licenses

## Script code
`BambuFilamentLibrary.py` and `bambu_data.py` — MIT License

Copyright (c) 2026 BambuFilamentLibrary contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Data
- **Filament colors** (names, hex codes, color codes): Bambu Studio, `resources/profiles/BBL/filament/filaments_color_codes.json`,
  https://github.com/bambulab/BambuStudio — © Bambu Lab, licensed under **AGPL-3.0**.
  `bambu_filaments.json` / `.csv` in this folder are derived from that file. The script downloads the current version at run time.
- **Filament densities** for lines without a data sheet: Bambu Studio filament profiles (same repository, AGPL-3.0).
- **Mechanical / thermal values**: Bambu Lab Filament Technical Data Sheets (published by Bambu Lab), summarized in `tds_all.json`.
  Values are Bambu's typical test values for reference only; printed parts depend on printer, settings and geometry.
- **Poisson's ratio, thermal conductivity, specific heat, thermal expansion**: generic literature values for each polymer family (not published by Bambu Lab).
  Mechanical values for PVA and support materials are estimates.

Bambu Lab, Bambu Studio and product names are trademarks of Bambu Lab. Autodesk and Fusion are trademarks of Autodesk, Inc.
This project is unofficial and not affiliated with or endorsed by Bambu Lab or Autodesk.
