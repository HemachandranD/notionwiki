Redesign this notion-wiki bridge. There are three layers Notion the source Bridge Daemon and LLm wiki itself.

1. The notion is where I keep my data,a articles, pages updated from anywhere remotely.
2. The Daemon periodically looks into my Notion and pulls the data and convert to md with support of dameon_log.md (similar to log.md in @llm_wiki.md) - sugegst improvements if required
3. The converted md is kept into typical llm wiki Raw Source layer (folder) which is immutable by agent @llm_wiki.md

