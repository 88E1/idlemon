# idlemon

A Pokemon Showdown bot for VGC / Champions doubles.

It logs into Showdown, queues battles, and picks moves each turn. Decisions can come from a fast heuristic, LLM call (I suggest Gemini Flash 3.5 since thinking models take too long and surpass battle timer).

Built on [foul-play](https://github.com/pmariglia/foul-play) (doubles fork).

## Run

```bash
python run.py \
  --websocket-uri wss://sim3.psim.us/showdown/websocket \
  --ps-username YOUR_NAME \
  --ps-password YOUR_PASSWORD \
  --bot-mode search_ladder \
  --pokemon-format gen9championsvgc2026regmb \
  --team-name gen9championsvgc2026regmb/sample \
```
