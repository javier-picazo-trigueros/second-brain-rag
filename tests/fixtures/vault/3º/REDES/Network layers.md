---
asignatura: REDES
curso: 3º
original: "[[Network layers.pdf]]"
resumen: "Overview of the OSI and TCP/IP layered models and what each layer is responsible for."
tags:
  - networking
conceptos_menores:
  - encapsulation
---

# Network layers

The OSI model splits communication into seven layers, and each layer only talks to the one above and the one below it. The TCP/IP model used on the internet groups them into four: link, internet, transport and application.

## Transport layer

The transport layer provides end-to-end delivery between processes. TCP gives reliable, ordered delivery with congestion control, while UDP is a thin wrapper that trades reliability for lower latency. Choosing between them depends on whether the application can tolerate lost packets.

## Encapsulation

When data moves down the stack, every layer adds its own header around the payload. The receiving host removes the headers in reverse order until the application gets the original data.
