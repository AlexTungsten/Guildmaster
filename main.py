from ui.game_loop import GameLoop

loop = GameLoop.create()

while True:
    loop.tick()
    print(loop.last_output)
    cmd = input("> ").strip()
    if cmd == "quit":
        break
    if cmd:
        print(loop.handle_input(cmd))