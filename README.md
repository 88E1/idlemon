# idlemon

A Pokemon Showdown agent for VGC / Champions doubles.

It autonomously logs into Showdown, queues battles, and picks moves each turn. Decisions can come from a fast heuristic, LLM call (I suggest Gemini Flash 3.5 since thinking models take too long and surpass battle timer).

## Demo

https://github.com/user-attachments/assets/ab51e463-ef14-4f5e-a442-9ece8319a602

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

## NOTE

I suggest using Cursor agent since you can easily access + monitor remotely on mobile (I did so during a date so take my word) + cheaper access to gemini 3.5 

Have fun :) 
