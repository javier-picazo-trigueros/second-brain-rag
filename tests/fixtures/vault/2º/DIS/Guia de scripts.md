---
asignatura: DIS
curso: 2º
tags:
  - scripts
---

# Guía de scripts

Notas sobre automatización. Los comentarios de shell y Python empiezan por `#` y no son encabezados.

## Script de despliegue

```bash
# Construye y levanta los contenedores
# Uso: ./deploy.sh
docker compose build
docker compose up -d
```

## Script en Python

```python
# Lee la configuración
## esto tampoco es un encabezado
def main() -> None:
    print("hola")
```

## Bloque con tildes

~~~
# otro comentario dentro de un bloque con tildes
echo listo
~~~

Después del código, el texto vuelve a ser normal y el encabezado siguiente sí cuenta.

## Limpieza

Eliminar contenedores parados con `docker system prune` después de comprobar qué se borrará.
