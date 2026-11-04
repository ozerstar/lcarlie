'use strict';
const assert=require('assert');
const {validateInternalReview}=require('./action-worker');
validateInternalReview({subject_ref:'fixture',reason:'review required'});
assert.throws(()=>validateInternalReview({subject_ref:'fixture',reason:'x',url:'https://invalid'}));
assert.throws(()=>validateInternalReview({subject_ref:'fixture',reason:'x',command:'bad'}));
assert.throws(()=>validateInternalReview({subject_ref:'fixture'}));
process.stdout.write('F5_HANDLER_TESTS|PASS|EXTERNAL_CALLS=0\n');
