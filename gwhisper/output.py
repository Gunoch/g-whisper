import time
import pyperclip
import keyboard


def type_text(text, method="clipboard", add_trailing_space=True):
    if not text:
        return
    if add_trailing_space:
        text = text + " "
    if method == "clipboard":
        _type_via_clipboard(text)
    elif method == "typing":
        keyboard.write(text)
    else:
        raise ValueError(f"method desconhecido: {method!r}")


def _type_via_clipboard(text):
    old_clipboard = None
    try:
        old_clipboard = pyperclip.paste()
    except Exception as e:
        print(f"[!] Falha ao ler clipboard (não será restaurado): {e}")

    try:
        pyperclip.copy(text)
    except Exception as e:
        print(f"[!] Falha ao escrever no clipboard: {e}")
        return

    time.sleep(0.1)
    try:
        keyboard.send("ctrl+v")
    except Exception as e:
        print(f"[!] Falha ao enviar Ctrl+V: {e}")
        return

    time.sleep(0.15)

    if old_clipboard is not None:
        try:
            pyperclip.copy(old_clipboard)
        except Exception as e:
            print(f"[!] Falha ao restaurar clipboard: {e}")
