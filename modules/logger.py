# modules/logger_cv.py

#En teroria esto deberia guardar los errores pero tambien seria bueno agregar descripciones de que paso 

import logging
from pathlib import Path
from datetime import datetime


def configurar_logger(nombre_logger="cv_maker"):
    """
    Configura un logger para guardar errores y eventos del CV Maker.
    Crea automáticamente la carpeta logs si no existe.
    """

    carpeta_logs = Path("logs")
    carpeta_logs.mkdir(exist_ok=True)

    fecha_actual = datetime.now().strftime("%Y-%m-%d")
    archivo_log = carpeta_logs / f"cv_maker_{fecha_actual}.log"

    logger = logging.getLogger(nombre_logger)
    logger.setLevel(logging.INFO)

    # Evita duplicar handlers si el logger ya fue configurado
    if logger.handlers:
        return logger

    formato = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(module)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    handler_archivo = logging.FileHandler(archivo_log, encoding="utf-8")
    handler_archivo.setLevel(logging.INFO)
    handler_archivo.setFormatter(formato)

    logger.addHandler(handler_archivo)

    return logger