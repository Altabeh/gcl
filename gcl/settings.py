from pathlib import Path
import logging

root_dir = Path(__file__).resolve().parents[1]

# ------------------ logging info ------------------

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
    datefmt="%m-%d %H:%M",
    filename=str(root_dir / f"{root_dir.name}.log"),
    filemode="a+",
)

console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter("%(name)-12s: %(levelname)-8s %(message)s"))
logger.addHandler(console)
