==============================================================
 Bambu Lab Filament Library for Autodesk Fusion
 User Guide (English)
==============================================================

This script adds the colors and material properties of every
Bambu Lab filament to Fusion. Each time it runs, it downloads
Bambu Lab's official data, so newly released filaments and colors
are added automatically.


--------------------------------------------------------------
1. What you get
--------------------------------------------------------------

 [Appearances] one per color
   - Uses Bambu's official color (hex) codes.
   - Surface finish matches the product: glossy, matte, silk,
     translucent, metallic.
   - Example name: Bambu PLA Basic - Jade White [10100]
     (the number in brackets is Bambu's color code)

 [Physical Materials] one per product line
   - Example names: Bambu PLA Basic, Bambu PETG HF, Bambu TPU 95A HF
   - Density, Young's modulus, strength and thermal values, for
     mass properties and simulation.
   - The material's Comments field lists the recommended nozzle/bed
     temperature, drying conditions and data source.

 Everything is added to Fusion "Favorites", so it is available in
 every design.

 Coverage (as of November 2026): PLA, PETG, ABS, ASA, TPU, PC,
 Nylon (PA), PET-CF, PPS-CF, PVA, support materials /
 342 colors, 48 product lines


--------------------------------------------------------------
2. Install
--------------------------------------------------------------

 1) Unzip the file. You get a folder named "BambuFilamentLibrary".

 2) Copy the whole folder to:

    Windows:
      %APPDATA%\Autodesk\Autodesk Fusion 360\API\Scripts\
      (paste this path into the File Explorer address bar, press Enter)

    Mac:
      ~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/

    Or in Fusion: Shift+S -> "Scripts and Add-Ins" -> the "+" button
    next to Scripts -> select the unzipped folder.


--------------------------------------------------------------
3. Run
--------------------------------------------------------------

 1) In Fusion, press Shift+S.
 2) Select "BambuFilamentLibrary" and click Run.
 3) A "Before you start" window opens first. Read the notice (the
    author is not responsible for problems caused by running it),
    tick the box and click "Agree and continue". Then the
    selection window opens.
      - The version and last update date are shown at the top.
      - Click the logo or "Credits" for the author (UDTT Studio)
        with GitHub and YouTube links.
      - Tabs at the top: [Filaments (colors)] / [Physical materials]
      - Filaments are grouped by family (PLA, PETG ...). Click a product
        line (PLA Basic, PLA Matte ...) to expand its colors.
      - Every item has a toggle. Family and line toggles, and the
        "Select all" toggle at the top, switch many at once.
      - Search by name, color code or hex. While searching,
        "Select all" applies only to the items found.
      - "installed" = already in Favorites, "outdated" = values changed.
      - At first, only the items you do not have yet are selected.
 4) Click "Install (n colors · m materials)". A new design opens, and
    the selected items are created and added to Favorites.
      - Installing everything takes 1-3 minutes.
      - Wait until the progress window closes.
 5) Optionally save the new design (e.g. "Bambu Filament Library")
    as a reference file. The items are already in Favorites either way.
 6) If "Recolor thumbnails to the real colors" is checked (bottom of
    the window), close Fusion after installing. Within about
    30 seconds the Favorites thumbnails are recolored. Open Fusion again
    to see them. (see section 4-1)

 * To check for new filaments, just run it again.
   Newly released colors are preselected in the window.
 * Without internet, the data bundled in the folder is used.
 * Reset (uninstall): click "Reset (remove all)" at the bottom left of
   the window, tick the box, click "Schedule reset" and close Fusion.
   About 10 seconds later every Bambu item is removed from Favorites
   (Fusion's API cannot remove favorites, so it runs after Fusion
   closes). The old library is kept as
   Favorites.adsklib.before-bambu-reset-<date>; your other favorites
   are added back the next time you run the script.
   Undo: close Fusion, delete Favorites.adsklib and rename the backup
   to Favorites.adsklib.


--------------------------------------------------------------
4. How to use
--------------------------------------------------------------

 1) Right-click a body -> "Physical Material" -> pick a material such
    as "Bambu PLA Basic" from Favorites. (mass, simulation)

 2) Press A (Appearance) -> drag "Bambu PLA Basic - <color>" from
    Favorites onto the body. (what you see on screen)

 * Materials are per product line, appearances are per color.
   In Fusion an appearance overrides the material's look, so this is
   the normal workflow. (The Fusion API cannot link a color to a
   material directly.)


--------------------------------------------------------------
4-1. Thumbnail colors
--------------------------------------------------------------

 Fusion cannot re-render the preview picture (thumbnail) of appearances
 created by a script, so they all start out white.

 If you click Yes on the "Recolor ..." question, the thumbnails inside
 the Favorites library file (Favorites.adsklib) are tinted with the real
 filament colors right after you close Fusion.
   - It runs after Fusion closes because Fusion keeps the file in use.
   - The original is backed up once as
     Favorites.adsklib.before-bambu-thumbnails
     (in %LOCALAPPDATA%\Autodesk\Common\Material Library\<version>\).
   - Log: thumbnail_log.txt in the script folder.
   - When new colors are added, the script asks again on the next run.

 To undo: close Fusion and rename the backup back to Favorites.adsklib.


--------------------------------------------------------------
5. When "outdated" entries are reported
--------------------------------------------------------------

 Fusion does not let scripts delete or overwrite Favorites. If Bambu
 changes a color or property, clean it up by hand:

 1) Open "last_report.txt" in the script folder to see the list.
 2) In Fusion Favorites, right-click each item -> Remove from Favorites.
 3) Run the script again. The items are added with the new values.


--------------------------------------------------------------
6. Settings (optional)
--------------------------------------------------------------

 Edit the top of BambuFilamentLibrary.py with any text editor.

   ONLINE_UPDATE = True     download the latest data on each run
   ADD_TO_FAVORITES = True  add items to Favorites
   FAMILIES = None          only some families,
                            e.g. FAMILIES = ("PLA", "PETG")
   TEST_MODE = False        True builds only a few samples
   RECOLOR_THUMBNAILS = True  offer to recolor thumbnails
   SHOW_SELECTOR = True     False = no window, install everything missing


--------------------------------------------------------------
7. Data sources and limits
--------------------------------------------------------------

 - Colors: Bambu Studio official color table (filaments_color_codes.json)
 - Properties: 35 official Bambu Lab Technical Data Sheets (TDS)
   - Lines without a data sheet use the closest product's values.
   - Brand-new lines are classified by name and use values from
     the same family.
   - Poisson's ratio, thermal conductivity, specific heat, thermal
     expansion, and the strength of PVA/support materials are not
     published by Bambu; typical values (estimates) are used.
 - Gradient/multicolor products use their first color only.
 - Hex colors are screen approximations; real filament may differ.
 - Property values are Bambu's test values for reference. Printed
   parts vary with printer, settings and geometry.


--------------------------------------------------------------
8. Other
--------------------------------------------------------------

 - Unofficial tool, not affiliated with Bambu Lab or Autodesk.
 - Sources and licenses: see NOTICE.md.
 - Run logs: last_run_log.txt and last_report.txt in the script folder.
 - Provided AS IS; the author is not responsible for any problem caused by running it.
 - Made by UDTT Studio (우당탕탕 스튜디오)
     YouTube: https://www.youtube.com/@udtt_studio
     GitHub:  https://github.com/mtenemy2/fusion-bambu-filament-library
