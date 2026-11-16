---
asignatura: Seguridad
curso: 4º
original: "[[Cortafuegos con iptables.pdf]]"
resumen: "Configuración de un cortafuegos en Linux con iptables: cadenas, políticas por defecto y reglas con estado."
tags:
  - seguridad
  - redes
conceptos:
  - "[[firewall]]"
---

# Cortafuegos con iptables

iptables filtra paquetes mediante reglas organizadas en tablas y cadenas. Las cadenas básicas son INPUT, OUTPUT y FORWARD, y cada una tiene una política por defecto (ACCEPT o DROP).

## Política restrictiva

Se empieza descartando todo el tráfico entrante y se permite solo lo necesario:

```bash
iptables -P INPUT DROP
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -p tcp --dport 22 -j ACCEPT
```

## Persistencia

Las reglas se pierden al reiniciar. En Debian se guardan con `iptables-save` y se restauran con `iptables-restore`. nftables es el sucesor de iptables, con una sintaxis unificada.
