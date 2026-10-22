"""Errores de dominio que la interfaz puede mostrar sin cerrarse."""


class UserError(Exception):
    """Condición esperada: nombre inválido, archivo ocupado o selección vacía."""


class ScanError(Exception):
    """Una imagen concreta no pudo leerse. El resto del análisis continúa."""

    def __init__(self, path: str, message: str) -> None:
        super().__init__(message)
        self.path = path
        self.message = message
