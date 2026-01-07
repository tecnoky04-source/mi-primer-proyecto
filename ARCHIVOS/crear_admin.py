# MEJORA DE CONSISTENCIA: Se asegura que el script utilice el módulo de base de datos correcto.
import sys
import os

# Agregar el directorio padre al path para imports correctos
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ARCHIVOS.app import create_app
from ARCHIVOS.database import user_repository
import getpass

def main():
    print("--- Creación de Usuario Administrador ---")
    username = input("Ingresa el nombre de usuario: ").strip().lower()
    if not username:
        print("\nError: El nombre de usuario no puede estar vacío.")
        return

    password = getpass.getpass("Ingresa la contraseña: ")
    if not password:
        print("\nError: La contraseña no puede estar vacía.")
        return

    password_confirm = getpass.getpass("Confirma la contraseña: ")
    if password != password_confirm:
        print("\nError: Las contraseñas no coinciden.")
        return

    # Crear un contexto de aplicación para acceder a la base de datos
    app = create_app()
    with app.app_context():
        try:
            # Usamos el repositorio para crear el usuario
            user_repository.create(username, password, role='admin')
            print(f"\n✅ Usuario Administrador '{username}' creado con éxito.")
        except Exception as e:
            print(f"\n❌ Error al crear el usuario: {e}")

if __name__ == "__main__":
    main()