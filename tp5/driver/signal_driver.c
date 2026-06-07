/*
 * signal_driver.c - CDD para TP5 Sistemas de Computación (UNC)
 * 
 * Character Device Driver que sensa dos señales simuladas con periodo de 1 segundo.
 * - Señal 0: Onda senoidal (simulada con tabla de valores)
 * - Señal 1: Onda cuadrada
 * 
 * write() -> selecciona cuál señal leer ("0" o "1")
 * read()  -> devuelve el valor actual de la señal seleccionada
 *
 * Grupo: apache-tevez
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/fs.h>
#include <linux/cdev.h>
#include <linux/device.h>
#include <linux/uaccess.h>
#include <linux/timer.h>
#include <linux/jiffies.h>
#include <linux/mutex.h>

#define DEVICE_NAME    "signal_sensor"
#define CLASS_NAME     "sdec"
#define SAMPLE_PERIOD_MS  1000  /* Periodo de muestreo: 1 segundo */

/* Tabla de seno (25 muestras, valores escalados 0-1000 representando 0.000 a 1.000) */
/* sin(x) para x = 0, 2*pi/25, 4*pi/25, ..., mapeado a [0, 1000] */
static const int sine_table[25] = {
    500, 618, 727, 818, 888, 935, 957, 952, 921, 867,
    794, 706, 609, 510, 412, 322, 244, 183, 142, 122,
    125, 152, 202, 271, 354
};

/* Variables del driver */
static dev_t dev_num;           /* Número major/minor */
static struct cdev my_cdev;      /* Estructura cdev */
static struct class *my_class;   /* Clase del dispositivo */
static struct device *my_device; /* Dispositivo */

/* Estado del sensado */
static int current_signal = 0;      /* 0 = señal senoidal, 1 = señal cuadrada */
static int signal0_value = 500;     /* Valor actual de la señal 0 */
static int signal1_value = 0;       /* Valor actual de la señal 1 */
static unsigned int sample_index = 0; /* Índice de muestreo */
static struct timer_list sample_timer; /* Timer del kernel para muestreo */
static DEFINE_MUTEX(driver_mutex);     /* Mutex para proteger acceso concurrente */

/* ---- Timer callback: se ejecuta cada 1 segundo ---- */
static void sample_timer_callback(struct timer_list *t)
{
    mutex_lock(&driver_mutex);

    /* Señal 0: Senoidal (recorre la tabla cíclicamente) */
    signal0_value = sine_table[sample_index % 25];

    /* Señal 1: Cuadrada (alterna entre 0 y 1000 cada 5 muestras) */
    signal1_value = ((sample_index / 5) % 2 == 0) ? 1000 : 0;

    sample_index++;

    mutex_unlock(&driver_mutex);

    /* Reprogramar el timer para el siguiente muestreo */
    mod_timer(&sample_timer, jiffies + msecs_to_jiffies(SAMPLE_PERIOD_MS));

    pr_info("signal_sensor: muestra #%u -> S0=%d, S1=%d\n",
            sample_index, signal0_value, signal1_value);
}

/* ---- File Operations ---- */

static int my_open(struct inode *inode, struct file *file)
{
    pr_info("signal_sensor: dispositivo abierto\n");
    return 0;
}

static int my_release(struct inode *inode, struct file *file)
{
    pr_info("signal_sensor: dispositivo cerrado\n");
    return 0;
}

/*
 * read() - Devuelve el valor de la señal seleccionada como texto.
 *          Formato: "SIGNAL=<n>,VALUE=<valor>,SAMPLE=<idx>\n"
 */
static ssize_t my_read(struct file *file, char __user *buf,
                       size_t count, loff_t *offset)
{
    char kbuf[128];
    int len;
    int val;
    int sig;
    unsigned int idx;

    if (*offset > 0)
        return 0;  /* EOF: ya se leyó todo */

    mutex_lock(&driver_mutex);
    sig = current_signal;
    val = (sig == 0) ? signal0_value : signal1_value;
    idx = sample_index;
    mutex_unlock(&driver_mutex);

    len = snprintf(kbuf, sizeof(kbuf),
                   "SIGNAL=%d,VALUE=%d,SAMPLE=%u\n", sig, val, idx);

    if (len > count)
        len = count;

    if (copy_to_user(buf, kbuf, len))
        return -EFAULT;

    *offset += len;
    return len;
}

/*
 * write() - Selecciona la señal a leer.
 *           Escribir "0" selecciona la señal senoidal.
 *           Escribir "1" selecciona la señal cuadrada.
 */
static ssize_t my_write(struct file *file, const char __user *buf,
                        size_t count, loff_t *offset)
{
    char kbuf[16];
    int new_signal;

    if (count == 0)
        return 0;

    if (count > sizeof(kbuf) - 1)
        count = sizeof(kbuf) - 1;

    if (copy_from_user(kbuf, buf, count))
        return -EFAULT;

    kbuf[count] = '\0';

    /* Parsear el valor: aceptar "0", "1", "0\n", "1\n" */
    if (kbuf[0] == '0')
        new_signal = 0;
    else if (kbuf[0] == '1')
        new_signal = 1;
    else {
        pr_warn("signal_sensor: valor inválido '%s'. Use 0 o 1.\n", kbuf);
        return -EINVAL;
    }

    mutex_lock(&driver_mutex);
    if (new_signal != current_signal) {
        current_signal = new_signal;
        pr_info("signal_sensor: señal cambiada a %d (%s)\n",
                new_signal, new_signal == 0 ? "senoidal" : "cuadrada");
    }
    mutex_unlock(&driver_mutex);

    return count;
}

static const struct file_operations fops = {
    .owner   = THIS_MODULE,
    .open    = my_open,
    .release = my_release,
    .read    = my_read,
    .write   = my_write,
};

/* ---- Constructor (insmod) ---- */
static int __init signal_driver_init(void)
{
    int ret;

    pr_info("signal_sensor: inicializando módulo (apache-tevez)\n");

    /* 1. Registrar rango <major, minor> dinámicamente */
    ret = alloc_chrdev_region(&dev_num, 0, 1, DEVICE_NAME);
    if (ret < 0) {
        pr_err("signal_sensor: error al registrar chrdev region\n");
        return ret;
    }
    pr_info("signal_sensor: registrado con major=%d, minor=%d\n",
            MAJOR(dev_num), MINOR(dev_num));

    /* 2. Inicializar y agregar cdev */
    cdev_init(&my_cdev, &fops);
    my_cdev.owner = THIS_MODULE;
    ret = cdev_add(&my_cdev, dev_num, 1);
    if (ret < 0) {
        pr_err("signal_sensor: error al agregar cdev\n");
        goto err_cdev;
    }

    /* 3. Crear clase (aparece en /sys/class/) */
    my_class = class_create(THIS_MODULE, CLASS_NAME);
    if (IS_ERR(my_class)) {
        pr_err("signal_sensor: error al crear clase\n");
        ret = PTR_ERR(my_class);
        goto err_class;
    }

    /* 4. Crear dispositivo (udev crea /dev/signal_sensor automáticamente) */
    my_device = device_create(my_class, NULL, dev_num, NULL, DEVICE_NAME);
    if (IS_ERR(my_device)) {
        pr_err("signal_sensor: error al crear dispositivo\n");
        ret = PTR_ERR(my_device);
        goto err_device;
    }

    /* 5. Iniciar timer de muestreo (cada 1 segundo) */
    timer_setup(&sample_timer, sample_timer_callback, 0);
    mod_timer(&sample_timer, jiffies + msecs_to_jiffies(SAMPLE_PERIOD_MS));

    pr_info("signal_sensor: módulo cargado exitosamente. /dev/%s creado.\n",
            DEVICE_NAME);
    return 0;

err_device:
    class_destroy(my_class);
err_class:
    cdev_del(&my_cdev);
err_cdev:
    unregister_chrdev_region(dev_num, 1);
    return ret;
}

/* ---- Destructor (rmmod) ---- */
static void __exit signal_driver_exit(void)
{
    /* Detener el timer */
    del_timer_sync(&sample_timer);

    /* Destruir en orden inverso a la creación */
    device_destroy(my_class, dev_num);
    class_destroy(my_class);
    cdev_del(&my_cdev);
    unregister_chrdev_region(dev_num, 1);

    pr_info("signal_sensor: módulo descargado (apache-tevez)\n");
}

module_init(signal_driver_init);
module_exit(signal_driver_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("apache-tevez (Joaquin Salinas, Facundo Avila, Candela Vergara)");
MODULE_DESCRIPTION("CDD para sensado de dos señales simuladas - TP5 SdeC UNC");
MODULE_VERSION("1.0");
