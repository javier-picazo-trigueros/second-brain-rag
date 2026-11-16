---
asignatura: SISTEMAS OPERATIVOS
curso: 1º
original: "[[Condiciones de carrera.pdf]]"
resumen: "Explica qué es una condición de carrera entre hilos y cómo evitarla con exclusión mutua, semáforos y estructuras sin estado compartido."
tags:
  - concurrencia
  - hilos
conceptos:
  - "[[condicion de carrera]]"
  - "[[semaforo]]"
conceptos_menores:
  - exclusión mutua
  - sección crítica
---

# Condiciones de carrera

Una condición de carrera aparece cuando el resultado de un programa depende del orden en que se intercalan las instrucciones de varios hilos que acceden a un mismo dato compartido.

## Qué es una condición de carrera

Dos hilos incrementan un contador global sin coordinarse. Cada incremento se compone de tres pasos: leer el valor, sumarle uno y escribirlo. Si ambos hilos leen el mismo valor antes de que cualquiera escriba, una de las actualizaciones se pierde. El fallo es intermitente y difícil de reproducir.

## Cómo evitar condiciones de carrera entre hilos

Hay tres estrategias principales para evitar que varios hilos corrompan un dato compartido.

### Exclusión mutua

Proteger la sección crítica con un cerrojo (mutex): solo un hilo puede estar dentro a la vez. Hay que adquirir el cerrojo antes de tocar el dato y liberarlo siempre, incluso si ocurre un error. Ver [[Semáforos y monitores]].

### Evitar el estado compartido

Si cada hilo trabaja con su propia copia de los datos y solo se combinan los resultados al final, no hay nada que proteger. Es la idea detrás de las variables locales al hilo y de los modelos de paso de mensajes.

### Operaciones atómicas

Para casos sencillos como un contador, las instrucciones atómicas del procesador (comparar e intercambiar) evitan el cerrojo y son más rápidas.
