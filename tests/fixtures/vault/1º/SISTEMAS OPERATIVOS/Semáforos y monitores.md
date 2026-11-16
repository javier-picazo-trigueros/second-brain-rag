---
asignatura: SISTEMAS OPERATIVOS
curso: 1º
original: "[[Semáforos y monitores.pdf]]"
resumen: "Semáforos binarios y contadores, monitores y variables de condición para sincronizar hilos."
tags: [concurrencia, sincronizacion]
conceptos:
  - "[[semaforo]]"
conceptos_menores:
  - variable de condición
---

# Semáforos y monitores #sincronizacion #so/hilos

Un semáforo es un contador entero con dos operaciones atómicas: `wait` decrementa y bloquea si el valor es cero, `signal` incrementa y despierta a un hilo en espera. Se usan para #exclusion-mutua y para ordenar la ejecución. Relacionado: [[Condiciones de carrera]].

## Semáforo binario

Con valor inicial uno actúa como cerrojo. Con valor inicial cero sirve para que un hilo espere a que otro termine una tarea.

```c
#include <semaphore.h>
#define N 4
sem_t mutex;  // # no es una etiqueta
sem_init(&mutex, 0, 1);
```

## Monitores

Un monitor agrupa datos y los procedimientos que los modifican, y garantiza que solo un hilo ejecuta código del monitor a la vez. Las variables de condición permiten esperar dentro del monitor hasta que se cumpla una condición, liberando el cerrojo mientras tanto. Lenguajes como Java lo ofrecen con `synchronized`, `wait` y `notify`.

El error típico es olvidar el bucle `while` alrededor de `wait`: hay que volver a comprobar la condición al despertar.
