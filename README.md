# notion-wiki

A one-way bridge that pulls your Notion workspace into the immutable Raw Sources layer of an LLM Wiki, so an assistant can build and maintain a compounding knowledge base on top. Inspired by [LLM Wiki](llm_wiki.md).

Install and run as a single cross-platform CLI:

```
uv tool install notion-wiki      # or: pipx install notion-wiki
notion-wiki init                 # interactive setup (alias: nw)
```

See [docs/design.md](docs/design.md) for the architecture.
