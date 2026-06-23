import { Chessground } from "@lichess-org/chessground";
import { Streamlit } from "streamlit-component-lib";

let ground = null;

function destsToMap(destsArg) {
  const map = new Map();
  if (destsArg) {
    for (const [orig, dests] of Object.entries(destsArg)) {
      map.set(orig, dests);
    }
  }
  return map;
}

function onRender(event) {
  const args = event.detail.args || {};
  const size = args.size || 480;

  const container = document.getElementById("board");
  container.style.width = `${size}px`;
  container.style.height = `${size}px`;

  const config = {
    fen: args.fen,
    orientation: args.orientation === "black" ? "black" : "white",
    lastMove: args.lastMove || undefined,
    movable: {
      free: false,
      color: "both",
      dests: destsToMap(args.dests),
      events: {
        after: (orig, dest) => {
          Streamlit.setComponentValue({ orig, dest });
        },
      },
    },
  };

  if (ground === null) {
    ground = Chessground(container, config);
  } else {
    ground.set(config);
  }

  Streamlit.setFrameHeight(size + 10);
}

Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, onRender);
Streamlit.setComponentReady();
Streamlit.setFrameHeight(490);
