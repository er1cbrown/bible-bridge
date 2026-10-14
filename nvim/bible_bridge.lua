-- Optional one-shot load if you are not using LazyVim plugins/:
--   :luafile ~/Desktop/bible-bridge/nvim/bible_bridge.lua
-- LazyVim users: the real spec is ~/.config/nvim/lua/plugins/bible.lua
-- Restart nvim or :Lazy reload bible-bridge

vim.notify(
  "Use LazyVim plugin lua/plugins/bible.lua  |  :Bible John 3:16  <leader>Bv",
  vim.log.levels.INFO
)
