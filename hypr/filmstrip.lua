-- Filmstrip uses native monocle for the main window and a shell thumbnail rail.
-- Monocle blocks input to inactive windows while retaining their full geometry
-- for toplevel capture. Merely overlapping Lua layout targets is not sufficient:
-- their rendering order and pointer hit-testing order can disagree.
-- The panel's exclusive zone reserves the sidebar; one window uses all space.
hl.config({ general = { layout = "monocle" } })
