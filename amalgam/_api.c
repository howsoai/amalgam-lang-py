#if !defined(_WIN32)
/* POSIX: pyconfig.h defines Py_GIL_DISABLED on free-threaded builds and has no link side effects. */
#include <pyconfig.h>
#endif
/* Windows: the compiler command line defines Py_GIL_DISABLED for free-threaded builds, and PC/pyconfig.h must
 * first be read after Py_LIMITED_API is settled, because it picks python3.lib or python3XY.lib at that point. */
#if !defined(Py_GIL_DISABLED)
#define Py_LIMITED_API 0x030B0000
#endif
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

/*
 * amalgam._api: calls the Amalgam engine's C entry points without copying Python str/bytes arguments.
 *
 * ctypes loads the engine library; amalgam._native passes this module the address of every entry point
 * in ENTRY_POINTS order. Every engine call releases the GIL. Text arguments point into the argument
 * objects' own buffers, which the call's argument tuple keeps alive for the duration of the call.
 *
 * The module is safe without the GIL: a Library is never modified after tp_new, there is no module or
 * static mutable state, and arguments are immutable str/bytes objects (or a buffer export held for the
 * call) whose memory is only borrowed while the call runs.
 *
 * The declarations below match src/Amalgam/Amalgam.h in the amalgam repository. The engine only reads
 * its char * inputs (it copies them into std::string or views them as std::string_view). Every char *
 * and char ** it returns is released with DeleteString.
 */

typedef struct {
    bool loaded;
    char *message;
    char *version;
    char **entity_path;
    size_t entity_path_len;
} AmlgLoadEntityStatus;

typedef struct {
    char *json;
    char *log;
} AmlgResultWithLog;

/* One function pointer type per engine entry point, named after the entry point. */
typedef void (*DeleteStringFunc)(char *);
typedef AmlgLoadEntityStatus (*LoadEntityFunc)(char *, char *, char *, bool, char *, char *, char *,
                                               const char **, size_t);
typedef AmlgLoadEntityStatus (*LoadEntityFromMemoryFunc)(char *, void *, size_t, char *, bool, char *, char *,
                                                         char *, const char **, size_t);
typedef AmlgLoadEntityStatus (*VerifyEntityFunc)(char *);
typedef char *(*GetEntityPermissionsFunc)(char *);
typedef bool (*SetEntityPermissionsFunc)(char *, char *);
typedef bool (*CloneEntityFunc)(char *, char *, char *, char *, bool, char *, char *, char *);
typedef bool (*StoreEntityFunc)(char *, char *, char *, bool, char *, const char **, size_t);
typedef bool (*StoreEntityToMemoryFunc)(char *, void **, size_t *, char *, bool, char *, const char **, size_t);
typedef void (*DestroyEntityFunc)(char *);
typedef bool (*SetRandomSeedFunc)(char *, char *);
typedef char **(*GetEntitiesFunc)(uint64_t *);
typedef void (*SetJSONToLabelFunc)(char *, char *, char *);
typedef char *(*GetJSONPtrFromLabelFunc)(char *, char *);
typedef char *(*ExecuteEntityJsonPtrFunc)(char *, char *, char *);
typedef AmlgResultWithLog (*ExecuteEntityJsonPtrLoggedFunc)(char *, char *, char *);
typedef char *(*EvalOnEntityFunc)(char *, char *);
typedef char *(*GetVersionStringFunc)(void);
typedef char *(*GetConcurrencyTypeStringFunc)(void);
typedef void (*SetSBFDataStoreEnabledFunc)(bool);
typedef bool (*IsSBFDataStoreEnabledFunc)(void);
typedef size_t (*GetMaxNumThreadsFunc)(void);
typedef void (*SetMaxNumThreadsFunc)(size_t);
typedef size_t (*GetNumActiveThreadsFunc)(void);
typedef char *(*GetGarbageCollectionParamsFunc)(void);
typedef void (*SetGarbageCollectionParamsFunc)(char *);

/*
 * The enum, the AmlgFunctions fields, entry_point_names, and the assignments in Library_new list the entry
 * points in the same order; that order is ENTRY_POINTS, the order of the addresses amalgam._native passes in.
 */
enum {
    AMLG_INDEX_DeleteString,
    AMLG_INDEX_LoadEntity,
    AMLG_INDEX_LoadEntityFromMemory,
    AMLG_INDEX_VerifyEntity,
    AMLG_INDEX_GetEntityPermissions,
    AMLG_INDEX_SetEntityPermissions,
    AMLG_INDEX_CloneEntity,
    AMLG_INDEX_StoreEntity,
    AMLG_INDEX_StoreEntityToMemory,
    AMLG_INDEX_DestroyEntity,
    AMLG_INDEX_SetRandomSeed,
    AMLG_INDEX_GetEntities,
    AMLG_INDEX_SetJSONToLabel,
    AMLG_INDEX_GetJSONPtrFromLabel,
    AMLG_INDEX_ExecuteEntityJsonPtr,
    AMLG_INDEX_ExecuteEntityJsonPtrLogged,
    AMLG_INDEX_EvalOnEntity,
    AMLG_INDEX_GetVersionString,
    AMLG_INDEX_GetConcurrencyTypeString,
    AMLG_INDEX_SetSBFDataStoreEnabled,
    AMLG_INDEX_IsSBFDataStoreEnabled,
    AMLG_INDEX_GetMaxNumThreads,
    AMLG_INDEX_SetMaxNumThreads,
    AMLG_INDEX_GetNumActiveThreads,
    AMLG_INDEX_GetGarbageCollectionParams,
    AMLG_INDEX_SetGarbageCollectionParams,
    AMLG_ENTRY_POINT_COUNT
};

typedef struct {
    DeleteStringFunc DeleteString;
    LoadEntityFunc LoadEntity;
    LoadEntityFromMemoryFunc LoadEntityFromMemory;
    VerifyEntityFunc VerifyEntity;
    GetEntityPermissionsFunc GetEntityPermissions;
    SetEntityPermissionsFunc SetEntityPermissions;
    CloneEntityFunc CloneEntity;
    StoreEntityFunc StoreEntity;
    StoreEntityToMemoryFunc StoreEntityToMemory;
    DestroyEntityFunc DestroyEntity;
    SetRandomSeedFunc SetRandomSeed;
    GetEntitiesFunc GetEntities;
    SetJSONToLabelFunc SetJSONToLabel;
    GetJSONPtrFromLabelFunc GetJSONPtrFromLabel;
    ExecuteEntityJsonPtrFunc ExecuteEntityJsonPtr;
    ExecuteEntityJsonPtrLoggedFunc ExecuteEntityJsonPtrLogged;
    EvalOnEntityFunc EvalOnEntity;
    GetVersionStringFunc GetVersionString;
    GetConcurrencyTypeStringFunc GetConcurrencyTypeString;
    SetSBFDataStoreEnabledFunc SetSBFDataStoreEnabled;
    IsSBFDataStoreEnabledFunc IsSBFDataStoreEnabled;
    GetMaxNumThreadsFunc GetMaxNumThreads;
    SetMaxNumThreadsFunc SetMaxNumThreads;
    GetNumActiveThreadsFunc GetNumActiveThreads;
    GetGarbageCollectionParamsFunc GetGarbageCollectionParams;
    SetGarbageCollectionParamsFunc SetGarbageCollectionParams;
} AmlgFunctions;

static const char *const entry_point_names[] = {
    "DeleteString",
    "LoadEntity",
    "LoadEntityFromMemory",
    "VerifyEntity",
    "GetEntityPermissions",
    "SetEntityPermissions",
    "CloneEntity",
    "StoreEntity",
    "StoreEntityToMemory",
    "DestroyEntity",
    "SetRandomSeed",
    "GetEntities",
    "SetJSONToLabel",
    "GetJSONPtrFromLabel",
    "ExecuteEntityJsonPtr",
    "ExecuteEntityJsonPtrLogged",
    "EvalOnEntity",
    "GetVersionString",
    "GetConcurrencyTypeString",
    "SetSBFDataStoreEnabled",
    "IsSBFDataStoreEnabled",
    "GetMaxNumThreads",
    "SetMaxNumThreads",
    "GetNumActiveThreads",
    "GetGarbageCollectionParams",
    "SetGarbageCollectionParams",
};

/* A negative array size is a compile error in every C dialect, including MSVC without /std:c11. */
typedef char entry_point_names_match_enum[
    (sizeof(entry_point_names) / sizeof(entry_point_names[0]) == AMLG_ENTRY_POINT_COUNT) ? 1 : -1];

typedef struct {
    PyObject_HEAD
    PyObject *owner;  /* the ctypes CDLL that loaded the engine library */
    AmlgFunctions fn;
} LibraryObject;

#define REQUIRE_ENTRY_POINT(self, name)                                                          \
    do {                                                                                         \
        if ((self)->fn.name == NULL) {                                                           \
            PyErr_SetString(PyExc_AttributeError,                                                \
                            "function '" #name "' not found in the Amalgam library");            \
            return NULL;                                                                         \
        }                                                                                        \
    } while (0)

/* PyArg_ParseTuple "O&" converter: str (as UTF-8) or bytes to a NUL-terminated const char *. */
static int
text_converter(PyObject *obj, void *result)
{
    const char **text = (const char **)result;
    if (PyUnicode_Check(obj)) {
        Py_ssize_t size;
        *text = PyUnicode_AsUTF8AndSize(obj, &size);
        return *text != NULL;
    }
    if (PyBytes_Check(obj)) {
        *text = PyBytes_AsString(obj);
        return *text != NULL;
    }
    PyErr_Format(PyExc_TypeError, "expected str or bytes, not %R", (PyObject *)Py_TYPE(obj));
    return 0;
}

static PyObject *
bytes_or_none(const char *value)
{
    if (value == NULL) {
        return Py_NewRef(Py_None);
    }
    return PyBytes_FromString(value);
}

/* Decodes engine text as UTF-8; NULL or invalid UTF-8 gives None. */
static PyObject *
str_or_none(const char *value)
{
    if (value == NULL) {
        return Py_NewRef(Py_None);
    }
    PyObject *result = PyUnicode_DecodeUTF8(value, (Py_ssize_t)strlen(value), "strict");
    if (result == NULL && PyErr_ExceptionMatches(PyExc_UnicodeDecodeError)) {
        PyErr_Clear();
        return Py_NewRef(Py_None);
    }
    return result;
}

/* Copies an engine-allocated string into bytes (None for NULL) and frees it. */
static PyObject *
take_string(LibraryObject *self, char *value)
{
    PyObject *result = bytes_or_none(value);
    if (value != NULL) {
        self->fn.DeleteString(value);
    }
    return result;
}

/* Converts an engine LoadEntityStatus to (loaded, message, version, [entity_path...]) and frees it. */
static PyObject *
take_load_status(LibraryObject *self, AmlgLoadEntityStatus status)
{
    PyObject *message = str_or_none(status.message);
    PyObject *version = message != NULL ? str_or_none(status.version) : NULL;
    PyObject *entity_path = version != NULL ? PyList_New(0) : NULL;
    int ok = entity_path != NULL;
    if (status.entity_path != NULL) {
        for (size_t i = 0; i < status.entity_path_len; i++) {
            if (ok) {
                PyObject *step = str_or_none(status.entity_path[i]);
                ok = step != NULL && PyList_Append(entity_path, step) == 0;
                Py_XDECREF(step);
            }
            if (status.entity_path[i] != NULL) {
                self->fn.DeleteString(status.entity_path[i]);
            }
        }
        self->fn.DeleteString((char *)status.entity_path);
    }
    if (status.message != NULL) {
        self->fn.DeleteString(status.message);
    }
    if (status.version != NULL) {
        self->fn.DeleteString(status.version);
    }
    PyObject *result = ok ? PyTuple_New(4) : NULL;
    if (result == NULL) {
        Py_XDECREF(message);
        Py_XDECREF(version);
        Py_XDECREF(entity_path);
        return NULL;
    }
    PyTuple_SetItem(result, 0, PyBool_FromLong(status.loaded));
    PyTuple_SetItem(result, 1, message);
    PyTuple_SetItem(result, 2, version);
    PyTuple_SetItem(result, 3, entity_path);
    return result;
}

/* A const char ** view of an entity path. `items` is a tuple snapshot that owns the strings. */
typedef struct {
    PyObject *items;
    const char **pointers;
    size_t length;
} EntityPath;

static void
entity_path_release(EntityPath *path)
{
    PyMem_Free((void *)path->pointers);
    Py_XDECREF(path->items);
    path->items = NULL;
    path->pointers = NULL;
    path->length = 0;
}

/* None or an empty sequence gives a NULL pointer and zero length. */
static int
entity_path_acquire(PyObject *obj, EntityPath *path)
{
    path->items = NULL;
    path->pointers = NULL;
    path->length = 0;
    if (obj == Py_None) {
        return 1;
    }
    path->items = PySequence_Tuple(obj);
    if (path->items == NULL) {
        return 0;
    }
    Py_ssize_t length = PyTuple_Size(path->items);
    if (length <= 0) {
        if (length < 0) {
            entity_path_release(path);
            return 0;
        }
        return 1;
    }
    path->pointers = (const char **)PyMem_Malloc(sizeof(const char *) * (size_t)length);
    if (path->pointers == NULL) {
        PyErr_NoMemory();
        entity_path_release(path);
        return 0;
    }
    for (Py_ssize_t i = 0; i < length; i++) {
        if (!text_converter(PyTuple_GetItem(path->items, i), (void *)&path->pointers[i])) {
            entity_path_release(path);
            return 0;
        }
    }
    path->length = (size_t)length;
    return 1;
}

static PyObject *
Library_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    char *keywords[] = {"owner", "addresses", NULL};
    PyObject *owner, *addresses;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "OO!:Library", keywords, &owner, &PyTuple_Type, &addresses)) {
        return NULL;
    }
    if (PyTuple_Size(addresses) != AMLG_ENTRY_POINT_COUNT) {
        PyErr_Format(PyExc_ValueError, "expected %d entry point addresses", AMLG_ENTRY_POINT_COUNT);
        return NULL;
    }
    void *pointers[AMLG_ENTRY_POINT_COUNT];
    for (Py_ssize_t i = 0; i < AMLG_ENTRY_POINT_COUNT; i++) {
        PyObject *address = PyTuple_GetItem(addresses, i);
        pointers[i] = address == Py_None ? NULL : PyLong_AsVoidPtr(address);
        if (pointers[i] == NULL && PyErr_Occurred()) {
            return NULL;
        }
    }
    if (pointers[AMLG_INDEX_DeleteString] == NULL) {
        PyErr_SetString(PyExc_ValueError, "the DeleteString entry point is required");
        return NULL;
    }
    allocfunc alloc = (allocfunc)PyType_GetSlot(type, Py_tp_alloc);
    LibraryObject *self = (LibraryObject *)alloc(type, 0);
    if (self == NULL) {
        return NULL;
    }
    self->owner = Py_NewRef(owner);
    self->fn.DeleteString = (DeleteStringFunc)pointers[AMLG_INDEX_DeleteString];
    self->fn.LoadEntity = (LoadEntityFunc)pointers[AMLG_INDEX_LoadEntity];
    self->fn.LoadEntityFromMemory = (LoadEntityFromMemoryFunc)pointers[AMLG_INDEX_LoadEntityFromMemory];
    self->fn.VerifyEntity = (VerifyEntityFunc)pointers[AMLG_INDEX_VerifyEntity];
    self->fn.GetEntityPermissions = (GetEntityPermissionsFunc)pointers[AMLG_INDEX_GetEntityPermissions];
    self->fn.SetEntityPermissions = (SetEntityPermissionsFunc)pointers[AMLG_INDEX_SetEntityPermissions];
    self->fn.CloneEntity = (CloneEntityFunc)pointers[AMLG_INDEX_CloneEntity];
    self->fn.StoreEntity = (StoreEntityFunc)pointers[AMLG_INDEX_StoreEntity];
    self->fn.StoreEntityToMemory = (StoreEntityToMemoryFunc)pointers[AMLG_INDEX_StoreEntityToMemory];
    self->fn.DestroyEntity = (DestroyEntityFunc)pointers[AMLG_INDEX_DestroyEntity];
    self->fn.SetRandomSeed = (SetRandomSeedFunc)pointers[AMLG_INDEX_SetRandomSeed];
    self->fn.GetEntities = (GetEntitiesFunc)pointers[AMLG_INDEX_GetEntities];
    self->fn.SetJSONToLabel = (SetJSONToLabelFunc)pointers[AMLG_INDEX_SetJSONToLabel];
    self->fn.GetJSONPtrFromLabel = (GetJSONPtrFromLabelFunc)pointers[AMLG_INDEX_GetJSONPtrFromLabel];
    self->fn.ExecuteEntityJsonPtr = (ExecuteEntityJsonPtrFunc)pointers[AMLG_INDEX_ExecuteEntityJsonPtr];
    self->fn.ExecuteEntityJsonPtrLogged =
        (ExecuteEntityJsonPtrLoggedFunc)pointers[AMLG_INDEX_ExecuteEntityJsonPtrLogged];
    self->fn.EvalOnEntity = (EvalOnEntityFunc)pointers[AMLG_INDEX_EvalOnEntity];
    self->fn.GetVersionString = (GetVersionStringFunc)pointers[AMLG_INDEX_GetVersionString];
    self->fn.GetConcurrencyTypeString = (GetConcurrencyTypeStringFunc)pointers[AMLG_INDEX_GetConcurrencyTypeString];
    self->fn.SetSBFDataStoreEnabled = (SetSBFDataStoreEnabledFunc)pointers[AMLG_INDEX_SetSBFDataStoreEnabled];
    self->fn.IsSBFDataStoreEnabled = (IsSBFDataStoreEnabledFunc)pointers[AMLG_INDEX_IsSBFDataStoreEnabled];
    self->fn.GetMaxNumThreads = (GetMaxNumThreadsFunc)pointers[AMLG_INDEX_GetMaxNumThreads];
    self->fn.SetMaxNumThreads = (SetMaxNumThreadsFunc)pointers[AMLG_INDEX_SetMaxNumThreads];
    self->fn.GetNumActiveThreads = (GetNumActiveThreadsFunc)pointers[AMLG_INDEX_GetNumActiveThreads];
    self->fn.GetGarbageCollectionParams =
        (GetGarbageCollectionParamsFunc)pointers[AMLG_INDEX_GetGarbageCollectionParams];
    self->fn.SetGarbageCollectionParams =
        (SetGarbageCollectionParamsFunc)pointers[AMLG_INDEX_SetGarbageCollectionParams];
    return (PyObject *)self;
}

static void
Library_dealloc(PyObject *self)
{
    PyTypeObject *type = Py_TYPE(self);
    Py_XDECREF(((LibraryObject *)self)->owner);
    freefunc tp_free = (freefunc)PyType_GetSlot(type, Py_tp_free);
    tp_free(self);
    Py_DECREF(type);
}

static PyObject *
Library_get_version_string(LibraryObject *self, PyObject *unused)
{
    REQUIRE_ENTRY_POINT(self, GetVersionString);
    char *result;
    Py_BEGIN_ALLOW_THREADS
    result = self->fn.GetVersionString();
    Py_END_ALLOW_THREADS
    return take_string(self, result);
}

static PyObject *
Library_get_concurrency_type_string(LibraryObject *self, PyObject *unused)
{
    REQUIRE_ENTRY_POINT(self, GetConcurrencyTypeString);
    char *result;
    Py_BEGIN_ALLOW_THREADS
    result = self->fn.GetConcurrencyTypeString();
    Py_END_ALLOW_THREADS
    return take_string(self, result);
}

static PyObject *
Library_get_garbage_collection_params(LibraryObject *self, PyObject *unused)
{
    REQUIRE_ENTRY_POINT(self, GetGarbageCollectionParams);
    char *result;
    Py_BEGIN_ALLOW_THREADS
    result = self->fn.GetGarbageCollectionParams();
    Py_END_ALLOW_THREADS
    return take_string(self, result);
}

static PyObject *
Library_is_sbf_datastore_enabled(LibraryObject *self, PyObject *unused)
{
    REQUIRE_ENTRY_POINT(self, IsSBFDataStoreEnabled);
    bool result;
    Py_BEGIN_ALLOW_THREADS
    result = self->fn.IsSBFDataStoreEnabled();
    Py_END_ALLOW_THREADS
    return PyBool_FromLong(result);
}

static PyObject *
Library_get_max_num_threads(LibraryObject *self, PyObject *unused)
{
    REQUIRE_ENTRY_POINT(self, GetMaxNumThreads);
    size_t result;
    Py_BEGIN_ALLOW_THREADS
    result = self->fn.GetMaxNumThreads();
    Py_END_ALLOW_THREADS
    return PyLong_FromSize_t(result);
}

static PyObject *
Library_get_num_active_threads(LibraryObject *self, PyObject *unused)
{
    REQUIRE_ENTRY_POINT(self, GetNumActiveThreads);
    size_t result;
    Py_BEGIN_ALLOW_THREADS
    result = self->fn.GetNumActiveThreads();
    Py_END_ALLOW_THREADS
    return PyLong_FromSize_t(result);
}

/* Returns the handles of the loaded entities as str; a NULL handle in the engine's array is read as "". */
static PyObject *
Library_get_entities(LibraryObject *self, PyObject *unused)
{
    REQUIRE_ENTRY_POINT(self, GetEntities);
    uint64_t count = 0;
    char **entities;
    Py_BEGIN_ALLOW_THREADS
    entities = self->fn.GetEntities(&count);
    Py_END_ALLOW_THREADS
    PyObject *result = PyList_New(0);
    int ok = result != NULL;
    if (entities != NULL) {
        for (uint64_t i = 0; i < count; i++) {
            if (ok) {
                const char *text = entities[i] != NULL ? entities[i] : "";
                PyObject *handle = PyUnicode_DecodeUTF8(text, (Py_ssize_t)strlen(text), "strict");
                ok = handle != NULL && PyList_Append(result, handle) == 0;
                Py_XDECREF(handle);
            }
            if (entities[i] != NULL) {
                self->fn.DeleteString(entities[i]);
            }
        }
        self->fn.DeleteString((char *)entities);
    }
    if (!ok) {
        Py_XDECREF(result);
        return NULL;
    }
    return result;
}

static PyObject *
Library_set_sbf_datastore_enabled(LibraryObject *self, PyObject *args)
{
    REQUIRE_ENTRY_POINT(self, SetSBFDataStoreEnabled);
    int enabled;
    if (!PyArg_ParseTuple(args, "p:set_sbf_datastore_enabled", &enabled)) {
        return NULL;
    }
    Py_BEGIN_ALLOW_THREADS
    self->fn.SetSBFDataStoreEnabled(enabled != 0);
    Py_END_ALLOW_THREADS
    Py_RETURN_NONE;
}

static PyObject *
Library_set_max_num_threads(LibraryObject *self, PyObject *args)
{
    REQUIRE_ENTRY_POINT(self, SetMaxNumThreads);
    Py_ssize_t max_num_threads;
    if (!PyArg_ParseTuple(args, "n:set_max_num_threads", &max_num_threads)) {
        return NULL;
    }
    if (max_num_threads < 0) {
        PyErr_SetString(PyExc_ValueError, "max_num_threads must not be negative");
        return NULL;
    }
    Py_BEGIN_ALLOW_THREADS
    self->fn.SetMaxNumThreads((size_t)max_num_threads);
    Py_END_ALLOW_THREADS
    Py_RETURN_NONE;
}

static PyObject *
Library_set_garbage_collection_params(LibraryObject *self, PyObject *args)
{
    REQUIRE_ENTRY_POINT(self, SetGarbageCollectionParams);
    const char *json_params;
    if (!PyArg_ParseTuple(args, "O&:set_garbage_collection_params", text_converter, &json_params)) {
        return NULL;
    }
    Py_BEGIN_ALLOW_THREADS
    self->fn.SetGarbageCollectionParams((char *)json_params);
    Py_END_ALLOW_THREADS
    Py_RETURN_NONE;
}

static PyObject *
Library_get_json_from_label(LibraryObject *self, PyObject *args)
{
    REQUIRE_ENTRY_POINT(self, GetJSONPtrFromLabel);
    const char *handle, *label;
    if (!PyArg_ParseTuple(args, "O&O&:get_json_from_label", text_converter, &handle, text_converter, &label)) {
        return NULL;
    }
    char *result;
    Py_BEGIN_ALLOW_THREADS
    result = self->fn.GetJSONPtrFromLabel((char *)handle, (char *)label);
    Py_END_ALLOW_THREADS
    return take_string(self, result);
}

static PyObject *
Library_set_json_to_label(LibraryObject *self, PyObject *args)
{
    REQUIRE_ENTRY_POINT(self, SetJSONToLabel);
    const char *handle, *label, *json;
    if (!PyArg_ParseTuple(args, "O&O&O&:set_json_to_label", text_converter, &handle, text_converter, &label,
                          text_converter, &json)) {
        return NULL;
    }
    Py_BEGIN_ALLOW_THREADS
    self->fn.SetJSONToLabel((char *)handle, (char *)label, (char *)json);
    Py_END_ALLOW_THREADS
    Py_RETURN_NONE;
}

static PyObject *
Library_get_entity_permissions(LibraryObject *self, PyObject *args)
{
    REQUIRE_ENTRY_POINT(self, GetEntityPermissions);
    const char *handle;
    if (!PyArg_ParseTuple(args, "O&:get_entity_permissions", text_converter, &handle)) {
        return NULL;
    }
    char *result;
    Py_BEGIN_ALLOW_THREADS
    result = self->fn.GetEntityPermissions((char *)handle);
    Py_END_ALLOW_THREADS
    return take_string(self, result);
}

static PyObject *
Library_set_entity_permissions(LibraryObject *self, PyObject *args)
{
    REQUIRE_ENTRY_POINT(self, SetEntityPermissions);
    const char *handle, *json_permissions;
    if (!PyArg_ParseTuple(args, "O&O&:set_entity_permissions", text_converter, &handle, text_converter,
                          &json_permissions)) {
        return NULL;
    }
    bool result;
    Py_BEGIN_ALLOW_THREADS
    result = self->fn.SetEntityPermissions((char *)handle, (char *)json_permissions);
    Py_END_ALLOW_THREADS
    return PyBool_FromLong(result);
}

static PyObject *
Library_destroy_entity(LibraryObject *self, PyObject *args)
{
    REQUIRE_ENTRY_POINT(self, DestroyEntity);
    const char *handle;
    if (!PyArg_ParseTuple(args, "O&:destroy_entity", text_converter, &handle)) {
        return NULL;
    }
    Py_BEGIN_ALLOW_THREADS
    self->fn.DestroyEntity((char *)handle);
    Py_END_ALLOW_THREADS
    Py_RETURN_NONE;
}

static PyObject *
Library_set_random_seed(LibraryObject *self, PyObject *args)
{
    REQUIRE_ENTRY_POINT(self, SetRandomSeed);
    const char *handle, *rand_seed;
    if (!PyArg_ParseTuple(args, "O&O&:set_random_seed", text_converter, &handle, text_converter, &rand_seed)) {
        return NULL;
    }
    bool result;
    Py_BEGIN_ALLOW_THREADS
    result = self->fn.SetRandomSeed((char *)handle, (char *)rand_seed);
    Py_END_ALLOW_THREADS
    return PyBool_FromLong(result);
}

static PyObject *
Library_eval_on_entity(LibraryObject *self, PyObject *args)
{
    REQUIRE_ENTRY_POINT(self, EvalOnEntity);
    const char *handle, *amlg;
    if (!PyArg_ParseTuple(args, "O&O&:eval_on_entity", text_converter, &handle, text_converter, &amlg)) {
        return NULL;
    }
    char *result;
    Py_BEGIN_ALLOW_THREADS
    result = self->fn.EvalOnEntity((char *)handle, (char *)amlg);
    Py_END_ALLOW_THREADS
    return take_string(self, result);
}

static PyObject *
Library_execute_entity_json(LibraryObject *self, PyObject *args)
{
    REQUIRE_ENTRY_POINT(self, ExecuteEntityJsonPtr);
    const char *handle, *label, *json;
    if (!PyArg_ParseTuple(args, "O&O&O&:execute_entity_json", text_converter, &handle, text_converter, &label,
                          text_converter, &json)) {
        return NULL;
    }
    char *result;
    Py_BEGIN_ALLOW_THREADS
    result = self->fn.ExecuteEntityJsonPtr((char *)handle, (char *)label, (char *)json);
    Py_END_ALLOW_THREADS
    return take_string(self, result);
}

static PyObject *
Library_execute_entity_json_logged(LibraryObject *self, PyObject *args)
{
    REQUIRE_ENTRY_POINT(self, ExecuteEntityJsonPtrLogged);
    const char *handle, *label, *json;
    if (!PyArg_ParseTuple(args, "O&O&O&:execute_entity_json_logged", text_converter, &handle, text_converter,
                          &label, text_converter, &json)) {
        return NULL;
    }
    AmlgResultWithLog result;
    Py_BEGIN_ALLOW_THREADS
    result = self->fn.ExecuteEntityJsonPtrLogged((char *)handle, (char *)label, (char *)json);
    Py_END_ALLOW_THREADS
    PyObject *json_result = take_string(self, result.json);
    if (json_result == NULL) {
        if (result.log != NULL) {
            self->fn.DeleteString(result.log);
        }
        return NULL;
    }
    PyObject *log = take_string(self, result.log);
    PyObject *pair = log != NULL ? PyTuple_New(2) : NULL;
    if (pair == NULL) {
        Py_XDECREF(json_result);
        Py_XDECREF(log);
        return NULL;
    }
    PyTuple_SetItem(pair, 0, json_result);
    PyTuple_SetItem(pair, 1, log);
    return pair;
}

static PyObject *
Library_load_entity(LibraryObject *self, PyObject *args)
{
    REQUIRE_ENTRY_POINT(self, LoadEntity);
    const char *handle, *file_path, *file_type, *json_file_params, *write_log, *print_log;
    int persist;
    PyObject *entity_path_obj;
    if (!PyArg_ParseTuple(args, "O&O&O&pO&O&O&O:load_entity", text_converter, &handle, text_converter, &file_path,
                          text_converter, &file_type, &persist, text_converter, &json_file_params, text_converter,
                          &write_log, text_converter, &print_log, &entity_path_obj)) {
        return NULL;
    }
    EntityPath entity_path;
    if (!entity_path_acquire(entity_path_obj, &entity_path)) {
        return NULL;
    }
    AmlgLoadEntityStatus status;
    Py_BEGIN_ALLOW_THREADS
    status = self->fn.LoadEntity((char *)handle, (char *)file_path, (char *)file_type, persist != 0,
                                 (char *)json_file_params, (char *)write_log, (char *)print_log,
                                 entity_path.pointers, entity_path.length);
    Py_END_ALLOW_THREADS
    entity_path_release(&entity_path);
    return take_load_status(self, status);
}

static PyObject *
Library_load_entity_from_memory(LibraryObject *self, PyObject *args)
{
    REQUIRE_ENTRY_POINT(self, LoadEntityFromMemory);
    const char *handle, *file_type, *json_file_params, *write_log, *print_log;
    PyObject *contents_obj, *entity_path_obj;
    if (!PyArg_ParseTuple(args, "O&OO&O&O&O&O:load_entity_from_memory", text_converter, &handle, &contents_obj,
                          text_converter, &file_type, text_converter, &json_file_params, text_converter, &write_log,
                          text_converter, &print_log, &entity_path_obj)) {
        return NULL;
    }
    Py_buffer contents;
    if (PyObject_GetBuffer(contents_obj, &contents, PyBUF_SIMPLE) < 0) {
        return NULL;
    }
    EntityPath entity_path;
    if (!entity_path_acquire(entity_path_obj, &entity_path)) {
        PyBuffer_Release(&contents);
        return NULL;
    }
    AmlgLoadEntityStatus status;
    Py_BEGIN_ALLOW_THREADS
    status = self->fn.LoadEntityFromMemory((char *)handle, contents.buf, (size_t)contents.len, (char *)file_type,
                                           false, (char *)json_file_params, (char *)write_log, (char *)print_log,
                                           entity_path.pointers, entity_path.length);
    Py_END_ALLOW_THREADS
    entity_path_release(&entity_path);
    PyBuffer_Release(&contents);
    return take_load_status(self, status);
}

static PyObject *
Library_verify_entity(LibraryObject *self, PyObject *args)
{
    REQUIRE_ENTRY_POINT(self, VerifyEntity);
    const char *file_path;
    if (!PyArg_ParseTuple(args, "O&:verify_entity", text_converter, &file_path)) {
        return NULL;
    }
    AmlgLoadEntityStatus status;
    Py_BEGIN_ALLOW_THREADS
    status = self->fn.VerifyEntity((char *)file_path);
    Py_END_ALLOW_THREADS
    return take_load_status(self, status);
}

static PyObject *
Library_clone_entity(LibraryObject *self, PyObject *args)
{
    REQUIRE_ENTRY_POINT(self, CloneEntity);
    const char *handle, *clone_handle, *file_path, *file_type, *json_file_params, *write_log, *print_log;
    int persist;
    if (!PyArg_ParseTuple(args, "O&O&O&O&pO&O&O&:clone_entity", text_converter, &handle, text_converter,
                          &clone_handle, text_converter, &file_path, text_converter, &file_type, &persist,
                          text_converter, &json_file_params, text_converter, &write_log, text_converter,
                          &print_log)) {
        return NULL;
    }
    bool result;
    Py_BEGIN_ALLOW_THREADS
    result = self->fn.CloneEntity((char *)handle, (char *)clone_handle, (char *)file_path, (char *)file_type,
                                  persist != 0, (char *)json_file_params, (char *)write_log, (char *)print_log);
    Py_END_ALLOW_THREADS
    return PyBool_FromLong(result);
}

static PyObject *
Library_store_entity(LibraryObject *self, PyObject *args)
{
    REQUIRE_ENTRY_POINT(self, StoreEntity);
    const char *handle, *file_path, *file_type, *json_file_params;
    int persist;
    PyObject *entity_path_obj;
    if (!PyArg_ParseTuple(args, "O&O&O&pO&O:store_entity", text_converter, &handle, text_converter, &file_path,
                          text_converter, &file_type, &persist, text_converter, &json_file_params,
                          &entity_path_obj)) {
        return NULL;
    }
    EntityPath entity_path;
    if (!entity_path_acquire(entity_path_obj, &entity_path)) {
        return NULL;
    }
    bool result;
    Py_BEGIN_ALLOW_THREADS
    result = self->fn.StoreEntity((char *)handle, (char *)file_path, (char *)file_type, persist != 0,
                                  (char *)json_file_params, entity_path.pointers, entity_path.length);
    Py_END_ALLOW_THREADS
    entity_path_release(&entity_path);
    return PyBool_FromLong(result);
}

static PyObject *
Library_store_entity_to_memory(LibraryObject *self, PyObject *args)
{
    REQUIRE_ENTRY_POINT(self, StoreEntityToMemory);
    const char *handle, *file_type, *json_file_params;
    PyObject *entity_path_obj;
    if (!PyArg_ParseTuple(args, "O&O&O&O:store_entity_to_memory", text_converter, &handle, text_converter,
                          &file_type, text_converter, &json_file_params, &entity_path_obj)) {
        return NULL;
    }
    EntityPath entity_path;
    if (!entity_path_acquire(entity_path_obj, &entity_path)) {
        return NULL;
    }
    void *data = NULL;
    size_t length = 0;
    Py_BEGIN_ALLOW_THREADS
    self->fn.StoreEntityToMemory((char *)handle, &data, &length, (char *)file_type, false,
                                 (char *)json_file_params, entity_path.pointers, entity_path.length);
    Py_END_ALLOW_THREADS
    entity_path_release(&entity_path);
    if (data == NULL) {
        Py_RETURN_NONE;
    }
    PyObject *result = PyBytes_FromStringAndSize((const char *)data, (Py_ssize_t)length);
    self->fn.DeleteString((char *)data);
    return result;
}

#define NOARGS(name) {#name, (PyCFunction)Library_##name, METH_NOARGS, NULL}
#define VARARGS(name) {#name, (PyCFunction)Library_##name, METH_VARARGS, NULL}

static PyMethodDef library_methods[] = {
    NOARGS(get_version_string),
    NOARGS(get_concurrency_type_string),
    NOARGS(is_sbf_datastore_enabled),
    VARARGS(set_sbf_datastore_enabled),
    NOARGS(get_max_num_threads),
    VARARGS(set_max_num_threads),
    NOARGS(get_num_active_threads),
    NOARGS(get_garbage_collection_params),
    VARARGS(set_garbage_collection_params),
    VARARGS(get_json_from_label),
    VARARGS(set_json_to_label),
    VARARGS(get_entity_permissions),
    VARARGS(set_entity_permissions),
    VARARGS(load_entity),
    VARARGS(load_entity_from_memory),
    VARARGS(verify_entity),
    VARARGS(clone_entity),
    VARARGS(store_entity),
    VARARGS(store_entity_to_memory),
    VARARGS(destroy_entity),
    VARARGS(set_random_seed),
    NOARGS(get_entities),
    VARARGS(execute_entity_json),
    VARARGS(execute_entity_json_logged),
    VARARGS(eval_on_entity),
    {NULL, NULL, 0, NULL},
};

static PyType_Slot library_slots[] = {
    {Py_tp_new, (void *)Library_new},
    {Py_tp_dealloc, (void *)Library_dealloc},
    {Py_tp_methods, library_methods},
    {Py_tp_doc, (void *)"Library(owner, addresses)\n--\n\n"
                        "Calls the Amalgam engine through entry point addresses ordered as ENTRY_POINTS."},
    {0, NULL},
};

static PyType_Spec library_spec = {
    "amalgam._api.Library",
    sizeof(LibraryObject),
    0,
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_IMMUTABLETYPE,
    library_slots,
};

static int
api_exec(PyObject *module)
{
    PyObject *names = PyTuple_New(AMLG_ENTRY_POINT_COUNT);
    if (names == NULL) {
        return -1;
    }
    for (Py_ssize_t i = 0; i < AMLG_ENTRY_POINT_COUNT; i++) {
        PyObject *name = PyUnicode_FromString(entry_point_names[i]);
        if (name == NULL) {
            Py_DECREF(names);
            return -1;
        }
        PyTuple_SetItem(names, i, name);
    }
    int status = PyModule_AddObjectRef(module, "ENTRY_POINTS", names);
    Py_DECREF(names);
    if (status < 0) {
        return -1;
    }
    PyObject *type = PyType_FromModuleAndSpec(module, &library_spec, NULL);
    if (type == NULL) {
        return -1;
    }
    status = PyModule_AddObjectRef(module, "Library", type);
    Py_DECREF(type);
    return status;
}

static PyModuleDef_Slot api_slots[] = {
    {Py_mod_exec, (void *)api_exec},
#ifdef Py_GIL_DISABLED
    /* Without this slot, importing the module re-enables the GIL for the whole process. */
    {Py_mod_gil, Py_MOD_GIL_NOT_USED},
#endif
    {0, NULL},
};

static struct PyModuleDef api_module = {
    PyModuleDef_HEAD_INIT,
    "amalgam._api",
    "C backend for calling the Amalgam engine.",
    0,
    NULL,
    api_slots,
    NULL,
    NULL,
    NULL,
};

PyMODINIT_FUNC
PyInit__api(void)
{
    return PyModuleDef_Init(&api_module);
}
