# 0018. Charts drawn by Observable Plot, and the map reads Earth Engine images

Status: accepted

## Context
The charts were drawn with Recharts: ticks such as 51, 35, 20 and dates such as 2001-05,
2003-05 that fell where the library put them, a slider under every chart, and no way to
compare two charts at the same date. The map showed only the areas over a basemap, so what a
mean was made of (its pixels, and the values around the area) could not be seen.

## Decision
Every chart is an Observable Plot figure inside one frame (`web/src/plot/`), which fits it to
its width, lists the values under the pointer, and exports it as SVG or 300 dpi PNG at a
journal's column width. Time charts share one date: hovering marks it on all of them, a click
chooses the month the map shows, and a drag zooms all of them to the same years.

The map draws a variable for one month from Earth Engine tiles (`/layers/{key}/tiles`, the
mean of the month's images in the variable's units, with its quality mask), reads the pixel
under a point over time (`/inspect`), and outlines the variable's own pixels over an area
(`/areas/{id}/pixels`). Tile URLs are kept in memory for an hour; points and pixel outlines go
to the results cache.

The month, layer and view are kept in the address, so a link opens the same view.

## Consequences
Charts carry clean ticks, units on the axis and their source, and look the same in a paper.
One more dependency (Plot, built on D3) replaces Recharts. Showing a layer or inspecting a
point is a live Earth Engine call: a second or two the first time, and none without a
connection.
