#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <dlfcn.h>

typedef char *(*ExecuteEntityJsonFunc)(const char *, const char *, const char *);
typedef void (*DeleteStringFunc)(char *);

static void *
get_dlsym(void *dlhandle, const char *symbol) {
    void *result = dlsym(dlhandle, symbol);
    if (result == NULL) {
        char *err = dlerror();
        if (err == NULL) {
            PyErr_Format(PyExc_RuntimeError, "could not load %s", symbol);
        } else {
            PyErr_Format(PyExc_RuntimeError, "could not load %s: %s", symbol, err);
        }
    }
    return result;
}

static PyObject *
api_execute_entity_json(PyObject *self, PyObject *args) {
    unsigned long dlhandle_i;
    /* These pointers are owned by Python, not copied, may come from either bytes or strings, and are UTF-8 encoded if strings. */
    const char *handle, *label, *json;
    Py_ssize_t handle_len, label_len, json_len;

    if (!PyArg_ParseTuple(args, "ks#s#s#", &dlhandle_i, &handle, &handle_len, &label, &label_len, &json, &json_len))
        return NULL;

    void *dlhandle = (void *)dlhandle_i;

    ExecuteEntityJsonFunc execute_entity_json = (ExecuteEntityJsonFunc)(get_dlsym(dlhandle, "ExecuteEntityJsonPtr"));
    if (!execute_entity_json) {
        return NULL;
    }
    char *result;
    Py_BEGIN_ALLOW_THREADS
    result = execute_entity_json(handle, label, json);
    Py_END_ALLOW_THREADS
    PyObject *value = Py_BuildValue("y", result);

    DeleteStringFunc delete_string = (DeleteStringFunc)(get_dlsym(dlhandle, "DeleteString"));
    if (!delete_string) {
        return NULL;
    }
    delete_string(result);

    return value;
}

static PyMethodDef ApiMethods[] = {
    {"execute_entity_json", api_execute_entity_json, METH_VARARGS, "Execute an Amalgam label with a parameter body."},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef apimodule = {
    PyModuleDef_HEAD_INIT,
    "_api",
    NULL, /* doc string */
    -1, /* per-interpreter module state size */
    ApiMethods
};

PyMODINIT_FUNC
PyInit__api(void) {
    return PyModule_Create(&apimodule);
}