# 42-Heilbronn-x-TUM-Programming-for-Management-Workshop

This repository contains the code and solutions for the Programming for Management Workshop, a collaboration between 42 Heilbronn and TUM.

## Project Structure

- `cards.py`, `evaluator.py`, `game.py`, `main.py`, `player.py`, `table.py`, `ui.py`: Main source files for the card game project.
- `workstations/`: instructions for each workstation 

## How to Run

1. **Requirements:**
	- Python 3.8 or higher

2. **Install dependencies:**
	```bash
	pip3 install flask
	```

3. **Run the CLI game:**
	```bash
	python3 main.py
	```

4. **Run the web app (single player + bots):**
	```bash
	python3 webapp.py
	```
	Then open `http://127.0.0.1:5000`.

5. **(Optional) Add card images to `static/cards`:**
	- File format: `PNG`
	- Card names: `AH.png`, `KD.png`, `7C.png`, etc.
	- Hidden card back: `back.png`
	- If an image is missing, the web app falls back to text on the card.

6. **Modules:**
	- Each module represents a component of the card game (e.g., player logic, game rules, table management).

## Contributing

Feel free to fork the repository and submit pull requests for improvements or bug fixes.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.