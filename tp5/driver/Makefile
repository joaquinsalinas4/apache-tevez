# Makefile para CDD signal_sensor - TP5 SdeC UNC
# Soporta compilación nativa y cross-compilation para ARM64

obj-m += signal_driver.o

# Detectar si estamos cross-compilando
# Uso:
#   make                    -> compila nativo (para probar en x86)
#   make CROSS=1            -> cross-compila para ARM64
#   make NATIVE_ARM=1       -> compila nativo dentro de la VM ARM64

ifdef CROSS
    # Cross-compilation desde x86 host hacia ARM64
    ARCH := arm64
    CROSS_COMPILE := aarch64-linux-gnu-
    KDIR := $(HOME)/tp5/kernel-headers-arm64
else ifdef NATIVE_ARM
    # Compilación nativa dentro de la VM ARM64
    KDIR := /lib/modules/$(shell uname -r)/build
else
    # Compilación nativa (x86 o cualquier arch)
    KDIR := /lib/modules/$(shell uname -r)/build
endif

PWD := $(shell pwd)

all:
	$(MAKE) -C $(KDIR) M=$(PWD) ARCH=$(ARCH) CROSS_COMPILE=$(CROSS_COMPILE) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) ARCH=$(ARCH) CROSS_COMPILE=$(CROSS_COMPILE) clean

# Ayuda para transferir a la VM
deploy:
	scp -P 2222 signal_driver.ko root@localhost:/root/

# Cargar módulo en la VM (ejecutar vía SSH)
load:
	ssh -p 2222 root@localhost 'insmod /root/signal_driver.ko && dmesg | tail -5'

unload:
	ssh -p 2222 root@localhost 'rmmod signal_driver && dmesg | tail -3'

status:
	ssh -p 2222 root@localhost 'lsmod | grep signal && cat /dev/signal_sensor'

.PHONY: all clean deploy load unload status
